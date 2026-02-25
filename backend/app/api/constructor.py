"""Constructor API endpoints for course creation workflow."""

import logging
import time
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, update

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.db.constructor.models import Course, Creator
from app.db.base import get_constructor_session
from app.api.auth import get_current_creator
from app.api.websocket import manager
from app.observability.langsmith import build_trace_config

# Import Constructor agents
from app.agents.constructor.main_agent.agent import main_agent

# Welcome message for new sessions
WELCOME_MESSAGE = (
    "Welcome to the Course Constructor! I'm here to help you build a comprehensive course. "
    "To get started, tell me about your course - what topic will it cover, who is the target audience, "
    "and what difficulty level are you aiming for?"
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/constructor", tags=["Constructor"])


def _is_llm_quota_error(exc: Exception) -> bool:
    """Detect provider quota/rate-limit errors from OpenAI-compatible backends."""
    text = str(exc).lower()
    return (
        "error code: 429" in text
        or "'code': '1113'" in text
        or "'code': '1302'" in text
        or "insufficient balance" in text
        or "no resource package" in text
        or "please recharge" in text
        or "rate limit reached" in text
    )


def _is_llm_connection_error(exc: Exception) -> bool:
    """Detect upstream LLM connectivity issues."""
    text = str(exc).lower()
    return (
        "connection error" in text
        or "connecterror" in text
        or "connection refused" in text
        or "winerror 10061" in text
        or "failed to establish a new connection" in text
    )


def _llm_unavailable_message() -> str:
    """User-facing fallback message for provider limit exhaustion."""
    return (
        "I can't generate an AI response right now because the LLM provider "
        "rejected the request due to limits (HTTP 429, e.g. rate-limit code 1302 "
        "or quota code 1113). Please wait and retry, or adjust plan/endpoint/key."
    )


def _llm_connection_message(settings: Settings) -> str:
    """User-facing message when the local LLM endpoint is unreachable."""
    return (
        "I can't reach the configured LLM endpoint right now. "
        f"Expected: {settings.LLM_BASE_URL}. "
        "If you're using LM Studio, make sure the local server is running and a model is loaded."
    )


def _resolve_creator_id(raw_creator_id: Any, session_id: str) -> Optional[int]:
    """Resolve creator_id from message payload or session identifier."""
    try:
        return int(raw_creator_id) if raw_creator_id else None
    except (TypeError, ValueError):
        return None


def _get_agent_name_from_namespace(namespace: tuple) -> str:
    """Extract a human-readable agent name from the namespace.

    Namespace format:
    - () -> Main agent
    - ("tools:abc123",) -> A subagent (extract from subagent metadata)
    - ("tools:abc123", "model_request:def456") -> Nested within subagent
    """
    if not namespace:
        return "Main Coordinator"

    # Look for the tools: segment which indicates a subagent
    for segment in namespace:
        if segment.startswith("tools:"):
            # Return a generic subagent name - the actual subagent type
            # will be communicated through the agent's messages
            return "Sub-Agent"

    return "Unknown Agent"


# ==============================================================================
# Pydantic Models
# ==============================================================================

class CourseInfo(BaseModel):
    """Basic course information."""
    title: str
    description: str
    difficulty: str = "beginner"


class FileUploadResponse(BaseModel):
    """Response for file upload."""
    file_id: str
    filename: str
    size: int
    status: str


class ConstructorSessionStart(BaseModel):
    """Start a new constructor session."""
    course_title: str | None = None
    course_description: str | None = None
    difficulty: str = "beginner"


class ConstructorChatMessage(BaseModel):
    """Message to the constructor agent."""
    message: str


class CoursePublishRequest(BaseModel):
    """Request to publish a course."""
    course_id: int


# ==============================================================================
# Session Management
# ==============================================================================

# In-memory session storage for deepagents
# Each session stores: {"messages": [], "thread_id": str}
_constructor_sessions: dict[str, dict[str, Any]] = {}


def get_constructor_session(session_id: str) -> dict[str, Any]:
    """Get or create a constructor session."""
    if session_id not in _constructor_sessions:
        _constructor_sessions[session_id] = {
            "messages": [],
            "thread_id": session_id,
        }
    return _constructor_sessions[session_id]


# ==============================================================================
# WebSocket Endpoint for Streaming with Subgraph Support
# ==============================================================================

@router.websocket("/session/ws/{session_id}")
async def constructor_websocket(
    websocket: WebSocket,
    session_id: str,
):
    """
    WebSocket endpoint for streaming Constructor Agent responses.

    This provides real-time, token-by-token streaming of agent responses
    with full subagent visibility using deepagents subgraph streaming.
    """
    settings = get_settings()
    await manager.connect(session_id, websocket)
    logger.info(f"Constructor WebSocket connected for session: {session_id}")

    # Track current agent for display purposes
    current_source = ""
    mid_line = False  # True when we've written tokens without a trailing newline

    try:
        logger.info("Starting WebSocket receive loop...")
        while True:
            # Receive messages from client
            try:
                raw_data = await websocket.receive()
                logger.info(f"WebSocket raw received: {raw_data}")
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected normally for session: {session_id}")
                break
            except Exception as recv_err:
                # Check if this is a disconnect-related error
                if "disconnect" in str(recv_err).lower() or "has been received" in str(recv_err):
                    logger.info(f"WebSocket disconnect message received for session: {session_id}")
                else:
                    logger.error(f"Error receiving from WebSocket: {recv_err}")
                break

            # Parse JSON from text frame
            if "text" in raw_data:
                import json
                try:
                    data = json.loads(raw_data["text"])
                except json.JSONDecodeError as je:
                    logger.error(f"Failed to parse JSON: {je}, raw: {raw_data['text'][:200]}")
                    continue
            else:
                data = raw_data

            logger.info(f"WebSocket parsed data: {data}")

            message_type = data.get("type", "message") if isinstance(data, dict) else "message"
            logger.info(f"Message type: {message_type}")

            if message_type == "message":
                user_message = data.get("message", "")
                if not user_message:
                    continue

                # Get session
                session = get_constructor_session(session_id)
                resolved_creator_id = _resolve_creator_id(data.get("creator_id"), session_id)

                # Store creator_id in session for future use
                if resolved_creator_id:
                    session["creator_id"] = resolved_creator_id

                # Build messages list - include creator_id context at the beginning
                from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

                messages = []

                # Add creator_id context as first message if available
                if session.get("creator_id"):
                    messages.append(SystemMessage(content=f"CREATOR_ID_CONTEXT: The current creator_id is {session['creator_id']}. "
                                   f"When you delegate to the ingestion-sub-agent, you must include this numeric value "
                                   f"in your task instruction so the sub-agent can call get_uploaded_files({session['creator_id']})."))

                # Add existing conversation history (convert dicts to proper Message objects)
                for msg in session["messages"]:
                    if isinstance(msg, dict):
                        if msg.get("role") == "user":
                            messages.append(HumanMessage(content=msg["content"]))
                        elif msg.get("role") == "assistant":
                            messages.append(AIMessage(content=msg["content"]))
                    elif isinstance(msg, (HumanMessage, AIMessage, SystemMessage)):
                        messages.append(msg)

                # Add the current user message
                messages.append(HumanMessage(content=user_message))

                # Update session messages (without the context prefix - that's added dynamically)
                session["messages"].append({
                    "role": "user",
                    "content": user_message,
                })

                # Prepare input for the agent - LangGraph expects proper state dict
                agent_input = {"messages": messages}

                logger.info(f"Processing message for session {session_id}")
                logger.info(f"Agent input: {agent_input}")

                # Send status update that processing has started
                await manager.send_status(
                    session_id,
                    "Processing your request...",
                    phase="processing",
                )

                # Helper function to format subagent names for display
                def _format_subagent_name(agent_name: str, node_name: str = "") -> str:
                    """Format agent/node name into a user-friendly display name."""
                    # Try to extract from agent_name first
                    name_to_use = agent_name or node_name

                    if not name_to_use or name_to_use == "constructor-main-agent":
                        return "Main Coordinator"

                    # Clean up the name
                    display = name_to_use.replace("-sub-agent", "").replace("_sub_agent", "").replace("_agent", "")
                    display = display.replace("_", " ").replace("-", " ")

                    # Handle specific known subagent names
                    display_lower = display.lower()
                    if "structure" in display_lower:
                        display = "Structure Sub-Agent"
                    elif "ingestion" in display_lower:
                        display = "Ingestion Sub-Agent"
                    elif "quiz" in display_lower or "quizgen" in display_lower:
                        display = "Quiz Generation Sub-Agent"
                    elif "validation" in display_lower:
                        display = "Validation Sub-Agent"
                    elif "general" in display_lower and "purpose" in display_lower:
                        display = "General Purpose Assistant"
                    else:
                        # Title case the display name
                        display = display.title().strip()

                    return display

                # Stream the agent execution with subgraph support
                try:
                    trace_config = build_trace_config(
                        thread_id=session_id,
                        tags=["constructor", "websocket"],
                        metadata={
                            "endpoint": "/api/v1/constructor/session/ws/{session_id}",
                            "session_id": session_id,
                            "creator_id": resolved_creator_id,
                        },
                        config={"recursion_limit": 1000},  # Increase recursion limit for deepagents
                    )

                    # Track subagent state for the stream
                    current_subagent = None
                    logger.info("Starting deepagent stream with astream_events...")
                    final_response_content = ""
                    current_ai_message_id = None
                    accumulated_tokens = ""
                    stream_counter = 0  # Unique counter for each message stream

                    # Track subagent state
                    active_subagents = {}  # subagent_id -> info
                    pending_tools = {}  # tool_call_id -> tool_name
                    last_stream_id = ""  # Track the last stream ID we sent tokens for

                    # Send agent thinking notification at start
                    await manager.broadcast_to_session(session_id, {"type": "agent_thinking", "agent": "Main Coordinator"})

                    # Use astream_events for detailed event streaming
                    async for event in main_agent.astream_events(
                        agent_input,
                        config=trace_config,
                        version="v1",
                    ):
                        event_type = event.get("event")
                        event_name = event.get("name", "")
                        event_data = event.get("data", {})

                        # Enhanced debug logging for key events
                        if event_type in ("on_chain_start", "on_chain_end", "on_tool_start", "on_tool_end"):
                            logger.info(f"Event: {event_type} | name={event_name} | metadata={event.get('metadata', {})}")

                        # Token-by-token streaming from LLM
                        if event_type == "on_chat_model_stream":
                            content_chunk = event_data.get("chunk", "")
                            if hasattr(content_chunk, "content"):
                                chunk_content = content_chunk.content
                                if isinstance(chunk_content, str) and chunk_content:
                                    # Check if this is a new message stream (not continuing previous)
                                    # by checking if accumulated_tokens was reset or we're starting fresh
                                    current_stream_id = f"stream_{stream_counter}"

                                    # Stream each token/character
                                    accumulated_tokens += chunk_content
                                    await manager.send_token(
                                        session_id,
                                        chunk_content,
                                        is_first=(len(accumulated_tokens) == len(chunk_content)),
                                        is_last=False,
                                        stream_id=current_stream_id,
                                    )

                        # LLM finished - send complete signal
                        elif event_type == "on_chat_model_end":
                            output = event_data.get("output")
                            if output:
                                if hasattr(output, "content"):
                                    final_response_content = output.content
                                elif isinstance(output, dict) and "content" in output:
                                    final_response_content = output["content"]

                            # Send empty token with is_last=True to mark stream completion
                            if accumulated_tokens:
                                current_stream_id = f"stream_{stream_counter}"
                                await manager.send_token(
                                    session_id,
                                    "",  # Empty content
                                    is_first=False,
                                    is_last=True,
                                    stream_id=current_stream_id,
                                )
                                # Reset for next message
                                accumulated_tokens = ""
                                stream_counter += 1

                        # Chain/agent started - detect subagent execution
                        elif event_type == "on_chain_start":
                            metadata = event.get("metadata", {})
                            # Check if this is a subagent starting
                            # The metadata may contain lc_agent_name or __langgraph_node__
                            agent_name = metadata.get("lc_agent_name", "")
                            node_name = metadata.get("__langgraph_node__", "")

                            # Determine if this is a subagent (not the main agent)
                            if agent_name and agent_name != "constructor-main-agent":
                                # This is likely a subagent starting
                                subagent_display = _format_subagent_name(agent_name, node_name)

                                # Only update if this is a new subagent or different from current
                                if subagent_display != "Main Coordinator" and subagent_display != current_subagent:
                                    subagent_id = f"subagent_{len(active_subagents)}_{event.get('run_id', '')}"
                                    active_subagents[subagent_id] = {
                                        "type": agent_name,
                                        "display_name": subagent_display,
                                        "description": f"Executing {subagent_display}",
                                        "started_at": event_data.get("time"),
                                    }
                                    await manager.send_subagent_start(
                                        session_id,
                                        subagent_id,
                                        subagent_display,
                                        f"Executing {subagent_display}",
                                    )
                                    current_subagent = subagent_display
                                    await manager.send_agent_change(session_id, subagent_display, True)
                                    logger.info(f"Subagent started via chain_start: {subagent_display} (agent_name={agent_name})")

                        # Tool call started
                        elif event_type == "on_tool_start":
                            tool_name = event_data.get("input", {}).get("name", event_name)
                            tool_args = event_data.get("input", {}).get("args", {})
                            tool_call_id = event_data.get("run_id")

                            if tool_name:
                                pending_tools[tool_call_id] = tool_name

                                # Debug: log all tool starts temporarily
                                logger.info(f"Tool start: {tool_name}, args keys: {list(tool_args.keys()) if isinstance(tool_args, dict) else 'not a dict'}")

                                # Debug: log write_todos specifically
                                if tool_name == "write_todos":
                                    logger.info(f"write_todos detected! tool_args type={type(tool_args)}, value={tool_args}")

                                # Skip internal tools from UI
                                if tool_name not in ("task", "write_todos", "read_file", "write_file", "edit_file", "glob", "grep", "ls", "execute"):
                                    await manager.send_tool_call(
                                        session_id,
                                        tool=tool_name,
                                        args=tool_args if isinstance(tool_args, dict) else {},
                                        agent=current_subagent or "Main Coordinator",
                                    )

                                # Handle write_todos tool specifically
                                if tool_name == "write_todos" and "todos" in tool_args:
                                    todos_list = tool_args["todos"]
                                    logger.info(f"Sending todo_update with {len(todos_list)} items")
                                    await manager.send_todo_update(
                                        session_id,
                                        [{"id": str(i), "task": str(t.get("content", t)), "status": t.get("status", "pending")}
                                             for i, t in enumerate(todos_list)]
                                    )

                                # Check if this is a subagent delegation (task tool)
                                # Just track it for completion - don't send duplicate subagent_start
                                # (on_chain_start already handles that)
                                if tool_name == "task":
                                    # Track for completion matching later
                                    subagent_id = tool_call_id or f"subagent_{len(active_subagents)}"
                                    active_subagents[subagent_id] = {
                                        "type": "task",
                                        "display_name": current_subagent or "Sub-Agent",
                                        "description": tool_args.get("description", ""),
                                        "started_at": event_data.get("time"),
                                    }

                        # Tool ended
                        elif event_type == "on_tool_end":
                            tool_name = event_name
                            tool_call_id = event_data.get("run_id")
                            tool_output = event_data.get("output", "")

                            # Resolve tool name from pending if needed
                            if tool_call_id and tool_call_id in pending_tools:
                                tool_name = pending_tools.pop(tool_call_id)

                            # Skip internal tools from UI
                            if tool_name not in ("task", "write_todos", "read_file", "write_file", "edit_file", "glob", "grep", "ls", "execute"):
                                await manager.send_tool_result(
                                    session_id,
                                    tool=tool_name,
                                    result=str(tool_output)[:1000],  # Truncate large outputs
                                    agent=current_subagent or "Main Coordinator",
                                )

                            # Clean up task tool tracking (but don't send completion - on_chain_end handles that)
                            if tool_name == "task" and tool_call_id in active_subagents:
                                active_subagents.pop(tool_call_id)


                        # Chain/node ended - check for state updates like todos
                        elif event_type == "on_chain_end":
                            metadata = event.get("metadata", {})
                            agent_name = metadata.get("lc_agent_name", "")

                            # Check if a subagent chain ended
                            if agent_name and agent_name != "constructor-main-agent" and current_subagent:
                                subagent_display = _format_subagent_name(agent_name, "")
                                # Only mark complete if this matches our current subagent
                                if current_subagent == subagent_display:
                                    await manager.send_subagent_complete(
                                        session_id,
                                        subagent_display,
                                        result="Sub-agent execution completed",
                                    )
                                    current_subagent = None
                                    await manager.send_agent_change(session_id, "Main Coordinator", False)
                                    logger.info(f"Subagent completed via chain_end: {subagent_display}")

                            # Check if the output contains todos
                            output = event_data.get("output", {})
                            if isinstance(output, dict):
                                if "todos" in output:
                                    todos = output["todos"]
                                    await manager.send_todo_update(
                                        session_id,
                                        [{"id": str(i), "task": str(t), "status": "pending"}
                                             for i, t in enumerate(todos)]
                                    )

                                # Also check nested output
                                for key, value in output.items():
                                    if isinstance(value, dict) and "todos" in value:
                                        todos = value["todos"]
                                        await manager.send_todo_update(
                                            session_id,
                                            [{"id": str(i), "task": str(t), "status": "pending"}
                                                 for i, t in enumerate(todos)]
                                        )

                    # Complete any pending subagent
                    if current_subagent:
                        await manager.send_subagent_complete(session_id, current_subagent)

                    # Store final response in session
                    if final_response_content:
                        session["messages"].append({
                            "role": "assistant",
                            "content": final_response_content,
                        })

                    # Send completion signal
                    await manager.broadcast_to_session(
                        session_id,
                        {"type": "line_break"}
                    )

                    await manager.broadcast_to_session(
                        session_id,
                        {"type": "stream_complete"}
                    )

                    current_source = ""
                    mid_line = False

                except Exception as e:
                    logger.error(f"Error in constructor stream: {e}", exc_info=True)
                    if _is_llm_quota_error(e):
                        fallback = _llm_unavailable_message()
                        await manager.send_token(
                            session_id,
                            fallback,
                            is_first=True,
                            is_last=True,
                            stream_id=f"{session_id}:llm-quota",
                        )
                    elif _is_llm_connection_error(e):
                        fallback = _llm_connection_message(settings)
                        await manager.send_token(
                            session_id,
                            fallback,
                            is_first=True,
                            is_last=True,
                            stream_id=f"{session_id}:llm-conn",
                        )
                    else:
                        await manager.send_error(
                            session_id,
                            f"Error processing request: {str(e)}",
                        )

            elif message_type == "start":
                # Initialize a new session
                get_constructor_session(session_id)

                await manager.send_token(
                    session_id,
                    WELCOME_MESSAGE,
                    is_first=True,
                    is_last=True,
                    stream_id=f"{session_id}:welcome",
                )

            elif message_type == "upload":
                # Handle file upload notification
                file_ids = data.get("file_ids", [])
                await manager.send_status(
                    session_id,
                    f"Processing {len(file_ids)} file(s)...",
                    phase="ingestion",
                )

                # The actual upload is handled via REST endpoint
                # This just triggers the ingestion agent

    except WebSocketDisconnect:
        manager.disconnect(session_id)
        logger.info(f"Constructor WebSocket disconnected for session: {session_id}")
    except Exception as e:
        logger.error(f"Error in constructor WebSocket: {e}", exc_info=True)
        manager.disconnect(session_id)


# ==============================================================================
# Constructor Session Endpoints (REST)
# ==============================================================================

@router.post("/session/start", status_code=status.HTTP_201_CREATED)
async def start_constructor_session(
    request: ConstructorSessionStart,
    current_creator: Creator = Depends(get_current_creator),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Start a new course construction session with the Constructor Agent.

    This initializes a new deepagents session for building a course.
    """
    session_id = f"constructor_{current_creator.id}_{int(time.time())}"

    # Initialize session
    get_constructor_session(session_id)

    # Add initial context if provided
    if request.course_title:
        session = get_constructor_session(session_id)
        session["messages"].append({
            "role": "user",
            "content": (
                f"I want to create a course titled '{request.course_title}'. "
                f"Description: {request.course_description or 'N/A'}. "
                f"Difficulty level: {request.difficulty}."
            ),
        })

    return {
        "session_id": session_id,
        "creator_id": current_creator.id,
        "message": WELCOME_MESSAGE,
        "status": "info_gathering",
        "websocket_url": f"/api/v1/constructor/session/ws/{session_id}",
    }


@router.post("/session/chat")
async def constructor_chat(
    request: ConstructorChatMessage,
    session_id: str = Query(...),
    current_creator: Creator = Depends(get_current_creator),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Send a message to the Constructor Agent and get a response.

    For streaming responses, use the WebSocket endpoint instead.
    This returns a complete response (non-streaming).
    """
    session = get_constructor_session(session_id)

    # Add user message
    session["messages"].append({
        "role": "user",
        "content": request.message,
    })

    try:
        # Invoke agent (non-streaming)
        trace_config = build_trace_config(
            thread_id=session_id,
            tags=["constructor", "rest"],
            metadata={
                "endpoint": "/api/v1/constructor/session/chat",
                "session_id": session_id,
                "creator_id": current_creator.id,
            },
        )

        result = await main_agent.ainvoke(
            {"messages": session["messages"][:]},
            config=trace_config,
        )

        # Extract AI response
        response_messages = result.get("messages", [])
        response = ""
        for msg in response_messages:
            if isinstance(msg, dict):
                if msg.get("role") == "assistant":
                    response = msg.get("content", "")
            elif hasattr(msg, "content"):
                response = str(msg.content)

        # Add assistant response to session
        if response:
            session["messages"].append({
                "role": "assistant",
                "content": response,
            })

        return {
            "session_id": session_id,
            "response": response or "I understand. Please continue.",
        }

    except Exception as e:
        logger.error(f"Error in constructor chat: {e}", exc_info=True)
        if _is_llm_quota_error(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_llm_unavailable_message(),
            )
        if _is_llm_connection_error(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_llm_connection_message(settings),
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}"
        )


@router.post("/session/upload")
async def upload_materials(
    session_id: str,
    files: list[UploadFile],
    current_creator: Creator = Depends(get_current_creator),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Upload course materials (PDFs, slides, videos) for processing.

    Files are stored and can be processed by the Ingestion Sub-Agent.
    Supports chunked uploads for large files.
    """
    import uuid

    from datetime import datetime

    uploaded_files = []

    # Create upload directory using absolute path
    upload_dir = settings.upload_absolute_path / "constructor" / str(current_creator.id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"[upload_materials] creator_id={current_creator.id}, upload_dir={upload_dir}")

    for file in files:
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        file_path = upload_dir / f"{file_id}_{file.filename}"

        try:
            # Validate file type
            file_ext = Path(file.filename).suffix.lower()
            allowed_types = {".pdf", ".ppt", ".pptx", ".docx", ".mp4", ".mov", ".avi", ".txt"}

            if file_ext not in allowed_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported file type: {file_ext}"
                )

            # Save file in chunks to avoid high memory usage on large uploads.
            file_size = 0
            chunk_size = 1024 * 1024  # 1MB
            with open(file_path, "wb") as f:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    file_size += len(chunk)
                    f.write(chunk)

            uploaded_files.append({
                "file_id": file_id,
                "filename": file.filename,
                "path": str(file_path),
                "size": file_size,
                "type": file_ext[1:],  # Remove dot
                "status": "uploaded",
            })

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error uploading file {file.filename}: {e}", exc_info=True)
            try:
                if file_path.exists():
                    file_path.unlink()
            except Exception:
                pass
            uploaded_files.append({
                "file_id": file_id,
                "filename": file.filename,
                "size": 0,
                "status": "error",
                "error": str(e),
            })

    # Store file info in session for the agent to access
    session = get_constructor_session(session_id)
    if "uploaded_files" not in session:
        session["uploaded_files"] = []
    session["uploaded_files"].extend(uploaded_files)

    return {
        "session_id": session_id,
        "uploaded_files": uploaded_files,
        "total_files": len(uploaded_files),
        "status": "uploaded",
        "message": f"Uploaded {len(uploaded_files)} file(s). You can now tell the agent to process them.",
    }


@router.get("/session/status/{session_id}")
async def get_session_status(
    session_id: str,
    current_creator: Creator = Depends(get_current_creator),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Get the current status of a construction session."""
    session = get_constructor_session(session_id)

    message_count = len(session.get("messages", []))
    file_count = len(session.get("uploaded_files", []))

    return {
        "session_id": session_id,
        "status": "active",
        "message_count": message_count,
        "uploaded_files_count": file_count,
    }


@router.post("/course/finalize")
async def finalize_course(
    request: CoursePublishRequest,
    current_creator: Creator = Depends(get_current_creator),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Finalize and publish a course.
    """

    async with get_constructor_session() as session:
        # Verify course belongs to creator without selecting optional/legacy columns.
        result = await session.execute(
            select(Course.id).where(
                Course.id == request.course_id,
                Course.creator_id == current_creator.id
            )
        )
        course_id = result.scalar_one_or_none()

        if course_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )

        # Update the course status
        await session.execute(
            update(Course)
            .where(Course.id == request.course_id)
            .values(is_published=True)
        )
        await session.commit()

        return {
            "course_id": request.course_id,
            "status": "published",
            "message": "Course published successfully!",
        }


@router.get("/courses")
async def list_courses(
    current_creator: Creator = Depends(get_current_creator),
    settings: Settings = Depends(get_settings)
) -> list[dict[str, Any]]:
    """List all courses for a creator."""

    async with get_constructor_session() as session:
        result = await session.execute(
            select(
                Course.id,
                Course.title,
                Course.description,
                Course.difficulty,
                Course.is_published,
                Course.created_at,
            ).where(Course.creator_id == current_creator.id)
        )
        courses = result.all()

        return [
            {
                "id": row.id,
                "title": row.title,
                "description": row.description,
                "difficulty": row.difficulty,
                "is_published": row.is_published,
                "created_at": row.created_at,
            }
            for row in courses
        ]


@router.get("/course/{course_id}")
async def get_course(
    course_id: int,
    current_creator: Creator = Depends(get_current_creator),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Get a specific course by ID."""

    async with get_constructor_session() as session:
        result = await session.execute(
            select(
                Course.id,
                Course.title,
                Course.description,
                Course.difficulty,
                Course.is_published,
                Course.created_at,
                Course.updated_at,
            ).where(
                Course.id == course_id,
                Course.creator_id == current_creator.id
            )
        )
        course = result.first()

        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )

        return {
            "id": course.id,
            "title": course.title,
            "description": course.description,
            "difficulty": course.difficulty,
            "is_published": course.is_published,
            "created_at": course.created_at,
            "updated_at": course.updated_at,
        }
