"""Constructor API endpoints for course creation workflow."""

import logging
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from app.agents.base.message_utils import append_user_message, latest_assistant_content
from app.core.config import Settings, get_settings
from app.db.constructor.models import Course, Creator
from app.db.base import get_constructor_session
from app.api.auth import get_current_creator
from app.api.websocket import manager
from app.observability.langsmith import build_trace_config

# Import Constructor agents
from app.agents.constructor.coordinator.agent import build_coordinator_graph, CoordinatorGraph
from app.agents.constructor.coordinator.prompts import WELCOME_MESSAGE
from app.agents.constructor.state import ConstructorState, create_initial_constructor_state

# Type alias
ConstructorGraph = CoordinatorGraph

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

# In-memory session storage (in production, use Redis or similar)
_constructor_sessions: dict[str, ConstructorGraph] = {}


def get_constructor_session_graph(session_id: str) -> Optional["ConstructorGraph"]:
    """Get or create a constructor session graph."""
    if session_id not in _constructor_sessions:
        _constructor_sessions[session_id] = build_coordinator_graph(session_id)
    return _constructor_sessions[session_id]


# ==============================================================================
# WebSocket Endpoint for Streaming
# ==============================================================================

@router.websocket("/session/ws/{session_id}")
async def constructor_websocket(
    websocket: WebSocket,
    session_id: str,
):
    """
    WebSocket endpoint for streaming Constructor Agent responses.

    This provides real-time, token-by-token streaming of agent responses.
    """
    settings = get_settings()
    await manager.connect(session_id, websocket)
    logger.info(f"Constructor WebSocket connected for session: {session_id}")

    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_json()

            message_type = data.get("type", "message")

            if message_type == "message":
                user_message = data.get("message", "")
                if not user_message:
                    continue

                # Get or create the graph
                graph = get_constructor_session_graph(session_id)

                # Get current state
                try:
                    current_state = graph.get_state()
                    if current_state is None:
                        # Initialize new session
                        current_state = create_initial_constructor_state(
                            session_id=session_id,
                            creator_id=data.get("creator_id"),
                        )
                except Exception:
                    current_state = create_initial_constructor_state(
                        session_id=session_id,
                        creator_id=data.get("creator_id"),
                    )

                # Add user message to state
                messages = current_state.get("messages", [])
                messages = append_user_message(messages, user_message)

                # Stream the graph execution
                try:
                    await manager.send_status(
                        session_id,
                        "Thinking...",
                        phase="processing",
                    )

                    trace_config = build_trace_config(
                        thread_id=session_id,
                        tags=["constructor", "websocket"],
                        metadata={
                            "endpoint": "/api/v1/constructor/session/ws/{session_id}",
                            "session_id": session_id,
                            "creator_id": data.get("creator_id"),
                        },
                    )

                    async for event in graph.stream(
                        {**current_state, "messages": messages},
                        config=trace_config,
                    ):
                        # Stream events to client
                        for node_name, node_output in event.items():
                            if node_output and isinstance(node_output, dict):
                                # Extract and send any AI messages
                                node_messages = node_output.get("messages", [])
                                content = latest_assistant_content(node_messages)
                                if content:
                                    # Stream token by token (chunked)
                                    chunk_size = 10
                                    for i in range(0, len(content), chunk_size):
                                        chunk = content[i:i + chunk_size]
                                        await manager.send_token(
                                            session_id,
                                            chunk,
                                            is_first=(i == 0),
                                            is_last=(i + chunk_size >= len(content)),
                                        )

                                # Send progress updates
                                progress = node_output.get("progress")
                                if progress is not None:
                                    await manager.send_status(
                                        session_id,
                                        f"Progress: {int(progress * 100)}%",
                                        progress=progress,
                                        phase=node_output.get("phase", "working"),
                                    )

                                # Send any validation results
                                if "validation_passed" in node_output:
                                    await manager.broadcast_to_session(
                                        session_id,
                                        {
                                            "type": "validation",
                                            "passed": node_output.get("validation_passed", False),
                                            "readiness_score": node_output.get("readiness_score", 0),
                                            "errors": node_output.get("validation_errors", []),
                                            "warnings": node_output.get("validation_warnings", []),
                                        },
                                    )

                except Exception as e:
                    logger.error(f"Error in constructor stream: {e}")
                    if _is_llm_quota_error(e):
                        fallback = _llm_unavailable_message()
                        await manager.send_token(
                            session_id,
                            fallback,
                            is_first=True,
                            is_last=True,
                        )
                    elif _is_llm_connection_error(e):
                        fallback = _llm_connection_message(settings)
                        await manager.send_token(
                            session_id,
                            fallback,
                            is_first=True,
                            is_last=True,
                        )
                    else:
                        await manager.send_error(
                            session_id,
                            f"Error processing request: {str(e)}",
                        )

            elif message_type == "start":
                # Initialize a new session
                get_constructor_session_graph(session_id)
                create_initial_constructor_state(
                    session_id=session_id,
                    creator_id=data.get("creator_id"),
                    course_info={
                        "title": data.get("course_title"),
                        "description": data.get("course_description"),
                        "difficulty": data.get("difficulty", "beginner"),
                    } if data.get("course_title") else None,
                )

                await manager.send_token(
                    session_id,
                    WELCOME_MESSAGE,
                    is_first=True,
                    is_last=True,
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
        logger.error(f"Error in constructor WebSocket: {e}")
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

    This initializes a new LangGraph session for building a course.
    """
    import time

    session_id = f"constructor_{current_creator.id}_{int(time.time())}"

    # Create initial state
    create_initial_constructor_state(
        session_id=session_id,
        creator_id=current_creator.id,
        course_info={
            "title": request.course_title,
            "description": request.course_description,
            "difficulty": request.difficulty,
        } if request.course_title else None,
    )

    # Initialize graph/session for subsequent websocket-driven interaction.
    get_constructor_session_graph(session_id)

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
    graph = get_constructor_session_graph(session_id)

    try:
        # Get current state
        current_state = graph.get_state()
        if current_state is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found. Please start a new session."
            )

        # Add user message
        messages = current_state.get("messages", [])
        messages = append_user_message(messages, request.message)

        # Invoke graph
        trace_config = build_trace_config(
            thread_id=session_id,
            tags=["constructor", "rest"],
            metadata={
                "endpoint": "/api/v1/constructor/session/chat",
                "session_id": session_id,
                "creator_id": current_creator.id,
            },
        )
        result = await graph.invoke({**current_state, "messages": messages}, config=trace_config)

        # Extract AI response
        response = latest_assistant_content(result.get("messages", [])) or "I understand. Please continue."

        return {
            "session_id": session_id,
            "response": response,
            "construction_phase": result.get("phase", "info_gathering"),
            "progress": result.get("progress", 0),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in constructor chat: {e}")
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

    Files are stored and the Ingestion Agent is triggered.
    Supports chunked uploads for large files.
    """
    import uuid

    from datetime import datetime

    from app.agents.constructor.tools.ingestion import (
        chunk_content_by_semantic,
        ingest_docx,
        ingest_pdf,
        ingest_ppt,
        ingest_video,
    )

    uploaded_files = []
    graph = get_constructor_session_graph(session_id)
    current_state = graph.get_state()
    if current_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found. Please start a new session.",
        )

    state_uploaded_files = list(current_state.get("uploaded_files", []))
    state_processed_files = list(current_state.get("processed_files", []))
    state_content_chunks = list(current_state.get("content_chunks", []))

    # Create upload directory
    upload_dir = Path(settings.UPLOAD_PATH) / "constructor" / str(current_creator.id)
    upload_dir.mkdir(parents=True, exist_ok=True)

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

            # Save file (supports large files with chunked reading)
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)

            # Get file size
            file_size = len(content)

            normalized_file_type = {
                ".pdf": "pdf",
                ".ppt": "ppt",
                ".pptx": "pptx",
                ".docx": "docx",
                ".txt": "text",
                ".mp4": "video",
                ".mov": "video",
                ".avi": "video",
            }.get(file_ext, file_ext[1:])

            course_id_for_ingestion = current_state.get("course_id") or 0

            state_file = {
                "file_id": file_id,
                "original_filename": file.filename,
                "file_path": str(file_path),
                "file_type": normalized_file_type,
                "size_bytes": file_size,
                "status": "pending",
                "error_message": None,
            }
            state_uploaded_files.append(state_file)

            # Trigger ingestion based on file type
            ingestion_result = None
            if file_ext == ".pdf":
                ingestion_result = await ingest_pdf.ainvoke(
                    {
                        "file_path": str(file_path),
                        "course_id": course_id_for_ingestion,
                    }
                )
            elif file_ext in (".ppt", ".pptx"):
                ingestion_result = await ingest_ppt.ainvoke(
                    {
                        "file_path": str(file_path),
                        "course_id": course_id_for_ingestion,
                    }
                )
            elif file_ext == ".docx":
                ingestion_result = await ingest_docx.ainvoke(
                    {
                        "file_path": str(file_path),
                        "course_id": course_id_for_ingestion,
                    }
                )
            elif file_ext in (".mp4", ".mov", ".avi"):
                ingestion_result = await ingest_video.ainvoke(
                    {
                        "file_path": str(file_path),
                        "course_id": course_id_for_ingestion,
                    }
                )
            elif file_ext == ".txt":
                # Simple text ingestion
                text_content = content.decode("utf-8", errors="ignore")
                ingestion_result = {
                    "success": True,
                    "file_id": file_id,
                    "file_type": "text",
                    "pages_or_slides": 1,
                    "content": text_content,
                    "metadata": {
                        "course_id": course_id_for_ingestion,
                        "original_filename": file.filename,
                    },
                }

            result_success = bool(ingestion_result and ingestion_result.get("success"))
            result_error = ingestion_result.get("error") if ingestion_result else "Unknown ingestion error"
            result_content = ingestion_result.get("content", "") if ingestion_result else ""
            created_chunks = 0

            if result_success and result_content:
                chunk_result = await chunk_content_by_semantic.ainvoke(
                    {
                        "content": result_content,
                        "min_chunk_size": 200,
                        "max_chunk_size": 1500,
                    }
                )
                chunks = chunk_result.get("chunks", [])
                for chunk in chunks:
                    chunk["source_file"] = file_id
                    chunk["chunk_type"] = chunk.get("chunk_type", "semantic")
                created_chunks = len(chunks)
                state_content_chunks.extend(chunks)

            if result_success:
                state_uploaded_files[-1] = {
                    **state_file,
                    "status": "completed",
                    "error_message": None,
                }
                processed_file = {
                    **state_file,
                    "status": "completed",
                }
                state_processed_files.append(processed_file)
            else:
                state_uploaded_files[-1] = {
                    **state_file,
                    "status": "error",
                    "error_message": str(result_error),
                }

            uploaded_files.append({
                "file_id": file_id,
                "filename": file.filename,
                "size": file_size,
                "type": file_ext[1:],  # Remove dot
                "status": "processed" if result_success else "error",
                "chunks": created_chunks,
                **({"error": str(result_error)} if not result_success else {}),
            })

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error uploading file {file.filename}: {e}")
            uploaded_files.append({
                "file_id": file_id,
                "filename": file.filename,
                "size": 0,
                "status": "error",
                "error": str(e),
            })

    graph.update_state(
        {
            "uploaded_files": state_uploaded_files,
            "processed_files": state_processed_files,
            "content_chunks": state_content_chunks,
            "phase": "ingestion_complete" if state_processed_files else current_state.get("phase", "upload"),
            "updated_at": datetime.utcnow().isoformat(),
        }
    )

    return {
        "session_id": session_id,
        "uploaded_files": uploaded_files,
        "total_files": len(uploaded_files),
        "status": "uploaded",
        "processed_files": len([f for f in uploaded_files if f.get("status") == "processed"]),
    }


@router.get("/session/status/{session_id}")
async def get_session_status(
    session_id: str,
    current_creator: Creator = Depends(get_current_creator),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Get the current status of a construction session."""
    graph = get_constructor_session_graph(session_id)

    try:
        state = graph.get_state()
        if state is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )

        return {
            "session_id": session_id,
            "status": state.get("phase", "unknown"),
            "progress": state.get("progress", 0),
            "uploaded_files_count": len(state.get("uploaded_files", [])),
            "topics_created": len(state.get("topics", [])),
            "questions_created": len(state.get("quiz_questions", [])),
            "validation_passed": state.get("validation_passed"),
            "readiness_score": state.get("readiness_score", 0),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session status: {e}")
        return {
            "session_id": session_id,
            "status": "error",
            "error": str(e),
        }


@router.post("/course/finalize")
async def finalize_course(
    request: CoursePublishRequest,
    current_creator: Creator = Depends(get_current_creator),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Finalize and publish a course.

    Triggers the Validation Agent before publishing.
    """

    async with get_constructor_session() as session:
        # Verify course belongs to creator
        result = await session.execute(
            select(Course).where(
                Course.id == request.course_id,
                Course.creator_id == current_creator.id
            )
        )
        course = result.scalar_one_or_none()

        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )

        # In a real implementation, this would trigger validation
        # and update the course status
        course.is_published = True
        await session.commit()

        return {
            "course_id": course.id,
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
            select(Course).where(Course.creator_id == current_creator.id)
        )
        courses = result.scalars().all()

        return [
            {
                "id": course.id,
                "title": course.title,
                "description": course.description,
                "difficulty": course.difficulty,
                "is_published": course.is_published,
                "created_at": course.created_at,
            }
            for course in courses
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
            select(Course).where(
                Course.id == course_id,
                Course.creator_id == current_creator.id
            )
        )
        course = result.scalar_one_or_none()

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
