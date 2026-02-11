"""State definitions for the Constructor workflow.

This module defines the TypedDict classes used by all Constructor agents.
"""

from datetime import datetime
import re
from typing import Annotated, Any, Dict, List, Optional

from langgraph.graph import add_messages
from typing_extensions import TypedDict


class CourseInfo(TypedDict):
    """Basic course information."""

    title: str
    description: str
    difficulty: str  # "beginner" | "intermediate" | "advanced"
    tags: List[str]


class UploadedFile(TypedDict):
    """Information about an uploaded file."""

    file_id: str
    original_filename: str
    file_path: str
    file_type: str  # "pdf" | "ppt" | "pptx" | "docx" | "video" | "text"
    size_bytes: int
    status: str  # "pending" | "processing" | "completed" | "error"
    error_message: Optional[str]


class TopicInfo(TypedDict):
    """Information about a learning topic."""

    id: Optional[int]
    title: str
    description: str
    content_summary: str
    prerequisites: List[int]  # Topic IDs
    unit_id: Optional[int]
    order_index: int


class UnitInfo(TypedDict):
    """Information about a course unit."""

    id: Optional[int]
    title: str
    description: str
    order_index: int
    topics: List[TopicInfo]


class QuizQuestionInfo(TypedDict):
    """Information about a quiz question."""

    id: Optional[int]
    topic_id: int
    question_text: str
    question_type: str  # "multiple_choice" | "true_false" | "short_answer"
    options: Optional[List[Dict[str, Any]]]  # For multiple choice
    correct_answer: str
    difficulty: str  # "easy" | "medium" | "hard"
    rubric: Optional[str]


class ConstructorState(TypedDict):
    """
    Complete state for the Constructor workflow.

    This state is managed by the Coordinator agent and passed to sub-agents.
    """

    # Conversation history
    messages: Annotated[List[Dict[str, Any]], add_messages]

    # Session identification
    session_id: str
    creator_id: int

    # Course being built
    course_id: Optional[int]
    course_info: CourseInfo

    # Construction phase
    phase: str  # "welcome" | "info_gathering" | "upload" | "ingestion" | "structuring" | "quiz_gen" | "validation" | "finalization" | "complete"

    # Uploaded materials
    uploaded_files: List[UploadedFile]
    processed_files: List[UploadedFile]

    # Course structure
    units: List[UnitInfo]
    topics: List[TopicInfo]
    quiz_questions: List[QuizQuestionInfo]

    # Sub-agent coordination
    current_agent: str  # "coordinator" | "ingestion" | "structure" | "quiz" | "validation"
    pending_subagent: Optional[str]
    subagent_results: Dict[str, Any]

    # Content chunks (from ingestion)
    content_chunks: List[Dict[str, Any]]

    # Progress tracking
    progress: float  # 0.0 to 1.0
    completion_percentage: float

    # Validation results
    validation_passed: bool
    validation_errors: List[str]
    validation_warnings: List[str]
    readiness_score: float  # 0.0 to 1.0

    # Error handling
    errors: List[str]

    # Timestamps
    created_at: str
    updated_at: str


def create_initial_constructor_state(
    session_id: str,
    creator_id: Optional[int],
    course_title: Optional[str] = None,
    course_info: Optional[Dict[str, Any]] = None,
) -> ConstructorState:
    """
    Create an initial Constructor state.

    Args:
        session_id: Unique session identifier
        creator_id: ID of the course creator
        course_title: Optional initial course title
        course_info: Optional initial course info payload with
            title, description, and difficulty fields

    Returns:
        Initial ConstructorState
    """
    now = datetime.utcnow().isoformat()

    initial_title = course_title or ""
    initial_description = ""
    initial_difficulty = "beginner"

    if course_info:
        initial_title = course_info.get("title") or initial_title
        initial_description = course_info.get("description") or ""
        initial_difficulty = course_info.get("difficulty") or "beginner"

    resolved_creator_id = resolve_creator_id(creator_id, session_id) or 0

    return ConstructorState(
        messages=[],
        session_id=session_id,
        creator_id=resolved_creator_id,
        course_id=None,
        course_info=CourseInfo(
            title=initial_title,
            description=initial_description,
            difficulty=initial_difficulty,
            tags=[],
        ),
        phase="welcome",
        uploaded_files=[],
        processed_files=[],
        units=[],
        topics=[],
        quiz_questions=[],
        current_agent="coordinator",
        pending_subagent=None,
        subagent_results={},
        content_chunks=[],
        progress=0.0,
        completion_percentage=0.0,
        validation_passed=False,
        validation_errors=[],
        validation_warnings=[],
        readiness_score=0.0,
        errors=[],
        created_at=now,
        updated_at=now,
    )


def resolve_creator_id(raw_creator_id: Any, session_id: str) -> Optional[int]:
    """Resolve creator_id from explicit value or constructor session_id."""
    try:
        if raw_creator_id is not None:
            parsed = int(raw_creator_id)
            if parsed > 0:
                return parsed
    except (TypeError, ValueError):
        pass

    match = re.match(r"^constructor_(\d+)_\d+$", str(session_id or ""))
    if match:
        try:
            parsed = int(match.group(1))
            if parsed > 0:
                return parsed
        except (TypeError, ValueError):
            return None
    return None
