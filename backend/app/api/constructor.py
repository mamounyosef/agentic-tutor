"""Constructor API endpoints for course creation workflow."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..core.config import Settings, get_settings

router = APIRouter(prefix="/constructor", tags=["Constructor"])


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


class ConstructorChatMessage(BaseModel):
    """Message to the constructor agent."""
    message: str
    session_id: str | None = None


# ==============================================================================
# Constructor Session Endpoints
# ==============================================================================

@router.post("/session/start", status_code=status.HTTP_201_CREATED)
async def start_constructor_session(
    request: ConstructorSessionStart,
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Start a new course construction session with the Constructor Agent.

    This initializes a new LangGraph session for building a course.
    """
    # TODO: Implement after LangGraph agents are created
    # 1. Initialize LangGraph checkpointer
    # 2. Create session record in database
    # 3. Return session_id and welcome message

    return {
        "session_id": "placeholder_session_id",
        "message": "Hello! I'm your Course Constructor Assistant. Let's build a course together!",
        "status": "info_gathering"
    }


@router.post("/session/chat")
async def constructor_chat(
    request: ConstructorChatMessage,
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Send a message to the Constructor Agent and get a response.

    This endpoint streams responses from the LangGraph agent.
    """
    # TODO: Implement after LangGraph agents are created
    # 1. Load conversation history from checkpointer
    # 2. Invoke LangGraph with message
    # 3. Stream response back to client
    # 4. Update checkpointer

    return {
        "session_id": request.session_id,
        "response": "I understand. Tell me more about your course.",
        "construction_phase": "info_gathering",
        "progress": 0
    }


@router.post("/session/upload")
async def upload_materials(
    files: list,
    session_id: str,
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Upload course materials (PDFs, slides, videos) for processing.

    Files are stored and the Ingestion Agent is triggered.
    """
    # TODO: Implement after file handling is created
    # 1. Validate file types
    # 2. Store files
    # 3. Trigger Ingestion Agent
    # 4. Return upload status

    return {
        "session_id": session_id,
        "uploaded_files": [],
        "status": "uploaded"
    }


@router.get("/session/status/{session_id}")
async def get_session_status(
    session_id: str,
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Get the current status of a construction session."""
    # TODO: Implement
    return {
        "session_id": session_id,
        "status": "in_progress",
        "progress": 0.5,
        "uploaded_files_count": 0,
        "topics_created": 0,
        "questions_created": 0
    }


@router.post("/course/finalize")
async def finalize_course(
    session_id: str,
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Finalize and publish a course.

    Triggers the Validation Agent before publishing.
    """
    # TODO: Implement after Validation Agent is created
    # 1. Trigger Validation Agent
    2. If valid: publish course
    # 3. If invalid: return validation errors

    return {
        "course_id": "placeholder_course_id",
        "status": "validation",
        "validation_errors": [],
        "validation_warnings": []
    }


@router.get("/courses")
async def list_courses(
    creator_id: int,
    settings: Settings = Depends(get_settings)
) -> list[dict[str, Any]]:
    """List all courses for a creator."""
    # TODO: Implement
    return []


@router.get("/course/{course_id}")
async def get_course(
    course_id: int,
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Get a specific course by ID."""
    # TODO: Implement
    return {}
