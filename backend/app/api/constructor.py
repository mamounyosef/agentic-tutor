"""Constructor API endpoints for course creation workflow."""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, update

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.db.constructor.models import Course, Creator
from app.db.base import get_constructor_session as get_constructor_db_session
from app.api.auth import get_current_creator
from app.api.websocket import manager
from app.observability.langsmith import build_trace_config

# Import Constructor agents
from app.agents.constructor.main_agent.agent import main_agent
from app.agents.constructor.tools.user_interaction_tools import (
    submit_user_answer,
    get_pending_question,
)

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


def _coerce_json_dict(value: Any) -> dict[str, Any]:
    """Best-effort conversion of tool payloads into a dict."""
    # Tool outputs may arrive as rich objects (e.g., with .content or model_dump()).
    if hasattr(value, "content"):
        nested = _coerce_json_dict(getattr(value, "content"))
        if nested:
            return nested
    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
        try:
            nested = _coerce_json_dict(value.model_dump())
            if nested:
                return nested
        except Exception:
            pass

    if isinstance(value, dict):
        # Common wrapper shape: {"content": "{\"question_id\": ...}"}
        if "content" in value and "question_id" not in value:
            nested = _coerce_json_dict(value.get("content"))
            if nested:
                return nested
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _extract_tool_name_and_args(event_name: str, event_data: dict[str, Any]) -> tuple[str, Any]:
    """Extract tool name and args from deepagents/langchain tool event payloads."""
    raw_input = event_data.get("input", {})
    tool_name = event_name

    if isinstance(raw_input, dict):
        maybe_name = raw_input.get("name")
        if isinstance(maybe_name, str) and maybe_name:
            tool_name = maybe_name

        # Some payloads are {"name": "...", "args": {...}}, others are plain args.
        raw_args = raw_input.get("args", raw_input)
        if isinstance(raw_args, (dict, list)):
            return tool_name, raw_args
        return tool_name, _coerce_json_dict(raw_args)

    if isinstance(raw_input, list):
        return tool_name, raw_input

    return tool_name, _coerce_json_dict(raw_input)


def _extract_tool_run_id(event: dict[str, Any], event_data: dict[str, Any]) -> Optional[str]:
    """Extract tool run_id from event-level or data-level payload."""
    run_id = event.get("run_id") or event_data.get("run_id")
    if run_id is None:
        return None
    return str(run_id)


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
    """Start a new constructor session.

    A course is automatically created when the session starts.
    You can provide initial course details or update them later.
    """
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
# Helper Functions for Todo Parsing
# ==============================================================================

async def _send_parsed_todos(session_id: str, todos: Any, manager) -> None:
    """Parse todos in any format and send to frontend."""
    if todos is None:
        return

    parsed_todos = []
    for i, t in enumerate(todos):
        if isinstance(t, dict):
            # deepagents format: {"content": "...", "status": "..."}
            content = t.get("content", str(t))
            status = t.get("status", "pending")
        elif isinstance(t, str):
            content = t
            status = "pending"
        else:
            content = str(t)
            status = "pending"

        parsed_todos.append({
            "id": str(i),
            "task": content,
            "status": status
        })

    logger.info(f"_send_parsed_todos: Sending {len(parsed_todos)} todos to frontend")
    await manager.send_todo_update(session_id, parsed_todos)


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

                # Build messages list - include creator_id and course_id context at the beginning
                from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

                messages = []

                # Add creator_id and course_id context as first message
                # Note: course_id is always available since session start auto-creates the course
                context_parts = []
                if session.get("creator_id"):
                    context_parts.append(f"creator_id is {session['creator_id']}")
                if session.get("course_id"):
                    context_parts.append(f"course_id is {session['course_id']}")

                if context_parts:
                    context_msg = f"SESSION_CONTEXT: The current {', '.join(context_parts)}. "
                    if session.get("course_id"):
                        context_msg += f"Files are stored in uploads/constructor/{session.get('creator_id', 'X')}/{session['course_id']}/. "
                        context_msg += f"When delegating to ingestion-sub-agent, include both creator_id ({session['creator_id']}) AND course_id ({session['course_id']}) so it can call get_uploaded_files(creator_id, course_id)."
                    messages.append(SystemMessage(content=context_msg))

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

                        # Debug: Log ALL events temporarily to see what we're getting
                        if event_type not in ("on_chat_model_start", "on_chat_model_stream", "on_chat_model_end"):
                            logger.info(f"Event: {event_type}, name: {event_name}")
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
                            tool_name, tool_args = _extract_tool_name_and_args(event_name, event_data)
                            tool_call_id = _extract_tool_run_id(event, event_data)

                            if tool_name:
                                if tool_call_id:
                                    pending_tools[tool_call_id] = tool_name

                                # Debug: log all tool starts temporarily
                                logger.info(f"Tool start: {tool_name}, args keys: {list(tool_args.keys()) if isinstance(tool_args, dict) else 'not a dict'}")

                                # ask_user popup is emitted on tool_end so we can use the real question_id.
                                if tool_name == "ask_user":
                                    logger.info(f"ask_user detected! tool_args: {tool_args}")

                                # Debug: log write_todos specifically - CRITICAL FOR IMMEDIATE UPDATE
                                if tool_name == "write_todos":
                                    logger.info(f"write_todos detected! tool_args type={type(tool_args)}, value={tool_args}")
                                    # Handle write_todos IMMEDIATELY to update frontend
                                    # The todos can be in different formats depending on how deepagents passes them
                                    todos_list = None
                                    if isinstance(tool_args, list):
                                        todos_list = tool_args
                                    elif isinstance(tool_args, dict):
                                        # Try different keys where todos might be
                                        for key in ["todos", "arg__todos", "input", "__arg__todos"]:
                                            if key in tool_args:
                                                todos_list = tool_args[key]
                                                logger.info(f"write_todos: found todos in key '{key}': {todos_list}")
                                                break

                                    logger.info(f"write_todos: extracted todos_list type={type(todos_list)}, value={todos_list}")

                                    # Parse and send todos immediately using helper
                                    if todos_list is not None:
                                        await _send_parsed_todos(session_id, todos_list, manager)

                                # Skip internal tools from UI (but write_todos and ask_user are handled above)
                                if tool_name not in ("task", "write_todos", "ask_user", "get_user_answer", "read_file", "write_file", "edit_file", "glob", "grep", "ls", "execute"):
                                    await manager.send_tool_call(
                                        session_id,
                                        tool=tool_name,
                                        args=tool_args if isinstance(tool_args, dict) else {},
                                        agent=current_subagent or "Main Coordinator",
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
                                        "description": tool_args.get("description", "") if isinstance(tool_args, dict) else "",
                                        "started_at": event_data.get("time"),
                                    }

                        # Tool ended
                        elif event_type == "on_tool_end":
                            tool_name = event_name
                            tool_call_id = _extract_tool_run_id(event, event_data)
                            tool_output = event_data.get("output", "")

                            # Resolve tool name from pending if needed
                            if tool_call_id and tool_call_id in pending_tools:
                                tool_name = pending_tools.pop(tool_call_id)

                            # Handle ask_user completion - now we have the real question_id from tool output.
                            if tool_name == "ask_user":
                                tool_output_dict = _coerce_json_dict(tool_output)
                                question_id = tool_output_dict.get("question_id")
                                if not isinstance(question_id, str):
                                    # Fallback for repr-style outputs like:
                                    # content='{"question_id":"..."}' name='ask_user'
                                    match = re.search(r'"question_id"\s*:\s*"([^"]+)"', str(tool_output))
                                    if match:
                                        question_id = match.group(1)
                                if isinstance(question_id, str) and question_id:
                                    pending_question = get_pending_question(question_id)
                                    if pending_question:
                                        await manager.send_question(
                                            session_id,
                                            question_id=question_id,
                                            question=str(pending_question.get("question", "")),
                                            choices=pending_question.get("choices", []) or [],
                                        )
                                        logger.info(f"Sent ask_user popup with question_id={question_id}")
                                    else:
                                        logger.warning(f"ask_user returned {question_id} but pending question was not found")
                                else:
                                    logger.warning(f"ask_user output missing question_id: {tool_output}")

                            # Skip internal tools from UI
                            if tool_name not in ("task", "write_todos", "ask_user", "get_user_answer", "read_file", "write_file", "edit_file", "glob", "grep", "ls", "execute"):
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

                            # IMPORTANT: Check for todos in chain output - this catches write_todos updates
                            output = event_data.get("output", {})
                            if isinstance(output, dict):
                                # Direct todos in output
                                if "todos" in output:
                                    todos = output["todos"]
                                    logger.info(f"Chain_end: Found direct todos: {todos}")
                                    await _send_parsed_todos(session_id, todos, manager)

                                # Check in messages array (deepagents stores state updates here)
                                if "messages" in output:
                                    messages = output["messages"]
                                    # Handle Overwrite objects and other LangGraph state objects safely
                                    messages_list = []
                                    try:
                                        # Try direct iteration first
                                        if isinstance(messages, list):
                                            messages_list = messages
                                        elif hasattr(messages, '__iter__') and not isinstance(messages, (str, dict)):
                                            # Check if it's an Overwrite-like object with actual values
                                            attr_val = getattr(messages, 'values', None)
                                            if attr_val is not None and callable(attr_val):
                                                # It's a dict-like object, call values() method
                                                val_result = attr_val()
                                                if hasattr(val_result, '__iter__'):
                                                    messages_list = list(val_result)
                                            else:
                                                # Try to convert to list, ignoring type errors for Overwrite objects
                                                messages_list = list(messages)  # type: ignore[arg-type, call-arg]
                                    except (TypeError, AttributeError):
                                        logger.info(f"Chain_end: Could not iterate messages, type={type(messages)}")

                                    for msg in messages_list:
                                        # Check for ToolMessage with todos
                                        if hasattr(msg, "content") and isinstance(msg.content, dict):
                                            if "todos" in msg.content:
                                                logger.info(f"Chain_end: Found todos in ToolMessage: {msg.content.get('todos')}")
                                                await _send_parsed_todos(session_id, msg.content["todos"], manager)
                                        elif isinstance(msg, dict):
                                            if "todos" in msg:
                                                logger.info(f"Chain_end: Found todos in message dict: {msg['todos']}")
                                                await _send_parsed_todos(session_id, msg["todos"], manager)

                                # Also check nested output
                                for key, value in output.items():
                                    if isinstance(value, dict) and "todos" in value:
                                        logger.info(f"Chain_end: Found todos in nested output[{key}]: {value['todos']}")
                                        await _send_parsed_todos(session_id, value["todos"], manager)

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

            elif message_type == "question_answer":
                # Handle user's response to a structured question
                question_id = data.get("question_id")
                answer = data.get("answer")
                answer_type = data.get("answer_type", "choice")  # "choice" or "other"

                logger.info(f"Received answer for question {question_id}: {answer} (type: {answer_type})")

                # Submit the answer to the pending question
                success = submit_user_answer(question_id, answer, answer_type)

                if success:
                    await manager.send_status(
                        session_id,
                        "Answer received. Processing...",
                        phase="processing",
                    )
                else:
                    await manager.send_error(
                        session_id,
                        f"Question {question_id} not found or already expired",
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

    A course is automatically created when the session starts.
    The course is created with default values that can be updated later.
    """
    from sqlalchemy import select

    # Generate session ID
    session_id = f"constructor_{current_creator.id}_{int(time.time())}"

    # Auto-create a course for this session
    # Use provided title or a default one
    course_title = request.course_title or f"New Course {int(time.time())}"
    course_description = request.course_description or "Course description will be updated during construction."

    async with get_constructor_db_session() as db_session:
        new_course = Course(
            creator_id=current_creator.id,
            title=course_title,
            description=course_description,
            difficulty=request.difficulty,
            is_published=False,
        )
        db_session.add(new_course)
        await db_session.commit()
        await db_session.refresh(new_course)
        course_id = new_course.id

    logger.info(f"Auto-created course {course_id} for creator {current_creator.id} at session start")

    # Initialize session with course_id
    session = get_constructor_session(session_id)
    session["creator_id"] = current_creator.id
    session["course_id"] = course_id
    session["course_title"] = course_title

    # Create the course upload directory
    upload_dir = settings.upload_absolute_path / "constructor" / str(current_creator.id) / str(course_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Created upload directory: {upload_dir}")

    # Add initial context if provided
    if request.course_title:
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
        "course_id": course_id,
        "course_title": course_title,
        "message": WELCOME_MESSAGE,
        "status": "ready",
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
    course_id: int = Query(..., description="Course ID to associate files with. A course is auto-created at session start."),
    current_creator: Creator = Depends(get_current_creator),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Upload course materials (PDFs, slides, videos) for processing.

    Files are organized by: uploads/constructor/{creator_id}/{course_id}/
    Each course has its own separate file storage.

    Note: A course is automatically created when the session starts,
    so course_id is always available.

    Files can be processed by the Ingestion Sub-Agent.
    Supports chunked uploads for large files.
    """
    import uuid

    from datetime import datetime

    uploaded_files = []

    # Create upload directory using absolute path
    # Structure: uploads/constructor/{creator_id}/{course_id}/
    upload_dir = settings.upload_absolute_path / "constructor" / str(current_creator.id) / str(course_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"[upload_materials] creator_id={current_creator.id}, course_id={course_id}, upload_dir={upload_dir}")

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
                "course_id": course_id,  # Include course_id in response
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

    # Store course_id in session for agent to use when calling tools
    # Note: course_id is always set since session start auto-creates the course
    session["course_id"] = course_id

    return {
        "session_id": session_id,
        "course_id": course_id,
        "uploaded_files": uploaded_files,
        "total_files": len(uploaded_files),
        "status": "uploaded",
        "message": f"Uploaded {len(uploaded_files)} file(s) to course {course_id}. You can now tell the agent to process them.",
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

    async with get_constructor_db_session() as session:
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

    async with get_constructor_db_session() as session:
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

    async with get_constructor_db_session() as session:
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
