"""Database persistence tools for the Constructor agent system.

These tools allow sub-agents to save course data directly to the database.
All tools are automatically traced with LangSmith when LANGCHAIN_TRACING_V2=true.

These tools use synchronous SQLAlchemy to avoid async/await issues with LangChain.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from langchain_core.tools import tool

from app.db.base import get_db_session
from app.db.constructor.models import Course, Module, Unit, Material, Quiz, QuizQuestion

logger = logging.getLogger(__name__)


def _sanitize_value(value: Any) -> Any:
    """Sanitize input values from LLM tool calls.

    LLMs may pass string "null" or "None" instead of actual None.
    This converts those to proper None values.
    """
    if isinstance(value, str):
        if value.lower() in ("null", "none", "undefined", ""):
            return None
    return value


def _sanitize_optional_int(value: Any) -> Optional[int]:
    """Sanitize optional integer values from LLM tool calls."""
    value = _sanitize_value(value)
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _sanitize_optional_list(value: Any) -> Optional[List]:
    """Sanitize optional list values from LLM tool calls."""
    value = _sanitize_value(value)
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        # Try to parse JSON string
        try:
            import json
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return None


@tool
def initialize_course(
    title: str,
    description: str,
    creator_id: int,
    difficulty: str = "beginner",
) -> str:
    """
    Initialize a new course in the database.

    Use this tool when starting to build a new course. It creates the course
    record and returns the course_id which should be used for all subsequent
    operations.

    Args:
        title: The title of the course
        description: A detailed description of the course
        creator_id: The ID of the creator creating this course
        difficulty: Course difficulty - "beginner", "intermediate", or "advanced"

    Returns:
        JSON string with course_id and status
    """
    session = get_db_session("constructor")

    try:
        course = Course(
            creator_id=creator_id,
            title=title,
            description=description,
            difficulty=difficulty,
            is_published=False,
        )
        session.add(course)
        session.commit()
        session.refresh(course)

        return json.dumps({
            "success": True,
            "course_id": course.id,
            "message": f"Course '{title}' created successfully."
        })
    except Exception as e:
        session.rollback()
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


@tool
def save_module(
    course_id: int,
    title: str,
    description: str,
    order_index: int,
    prerequisites: Any = None,
) -> str:
    """
    Create a module within a course (e.g., "Week 1", "Foundations").

    Modules are the top-level divisions within a course. Each module
    contains multiple units.

    Args:
        course_id: The ID of the course
        title: Module title (e.g., "Week 1: Introduction")
        description: Module description
        order_index: The order of this module within the course
        prerequisites: List of module IDs that must be completed first (as JSON array or null)

    Returns:
        JSON string with module_id and status
    """
    session = get_db_session("constructor")

    try:
        # Sanitize prerequisites
        prerequisites_clean = _sanitize_optional_list(prerequisites)

        module = Module(
            course_id=course_id,
            title=title,
            description=description,
            order_index=order_index,
            prerequisites=prerequisites_clean,
        )
        session.add(module)
        session.commit()
        session.refresh(module)

        return json.dumps({
            "success": True,
            "module_id": module.id,
            "message": f"Module '{title}' saved successfully."
        })
    except Exception as e:
        session.rollback()
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


@tool
def save_unit(
    module_id: int,
    title: str,
    description: str,
    order_index: int,
    prerequisites: Any = None,
) -> str:
    """
    Create a unit within a module.

    Units are the content containers within a module. Each unit
    contains the actual learning content (materials, videos, PDFs, etc.).

    Args:
        module_id: The ID of the module this unit belongs to
        title: Unit title (e.g., "Introduction to Variables")
        description: Unit description
        order_index: The order of this unit within the module
        prerequisites: List of unit IDs that must be completed first (as JSON array or null)

    Returns:
        JSON string with unit_id and status
    """
    session = get_db_session("constructor")

    try:
        # Sanitize prerequisites
        prerequisites_clean = _sanitize_optional_list(prerequisites)

        unit = Unit(
            module_id=module_id,
            title=title,
            description=description,
            order_index=order_index,
            prerequisites=prerequisites_clean,
        )
        session.add(unit)
        session.commit()
        session.refresh(unit)

        return json.dumps({
            "success": True,
            "unit_id": unit.id,
            "message": f"Unit '{title}' saved successfully."
        })
    except Exception as e:
        session.rollback()
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


@tool
def save_material(
    course_id: int,
    unit_id: Any = None,
    material_type: str = "other",
    file_path: str = "",
    original_filename: str = "",
    title: Any = None,
    description: Any = None,
    duration_seconds: Any = None,
    page_count: Any = None,
) -> str:
    """
    Save a material (video, PDF, slides, etc.) to a course.

    This stores the file path so the frontend can display the content
    to students. The actual file is stored on disk.

    Args:
        course_id: The ID of the course
        unit_id: The ID of the unit this material belongs to (can be None initially)
        material_type: Type - "video", "pdf", "ppt", "pptx", "docx", "text", or "other"
        file_path: Full path to the stored file on disk
        original_filename: Original name of the uploaded file
        title: Optional title for the material
        description: Optional description of the material content
        duration_seconds: For videos - duration in seconds (as string or int)
        page_count: For PDFs/slides - number of pages (as string or int)

    Returns:
        JSON string with material_id and status
    """
    session = get_db_session("constructor")

    try:
        # Sanitize optional integer parameters
        unit_id_clean = _sanitize_optional_int(unit_id)
        duration_clean = _sanitize_optional_int(duration_seconds)
        page_count_clean = _sanitize_optional_int(page_count)
        title_clean = _sanitize_value(title)
        description_clean = _sanitize_value(description)

        # Build metadata JSON
        metadata = {}
        if title_clean:
            metadata["title"] = title_clean
        if description_clean:
            metadata["description"] = description_clean
        if duration_clean:
            metadata["duration_seconds"] = duration_clean
        if page_count_clean:
            metadata["page_count"] = page_count_clean

        material = Material(
            course_id=course_id,
            unit_id=unit_id_clean,
            material_type=material_type,
            file_path=file_path,
            original_filename=original_filename,
            course_metadata=metadata if metadata else None,
            processing_status="completed",
            chunks_count=0,
        )
        session.add(material)
        session.commit()
        session.refresh(material)

        return json.dumps({
            "success": True,
            "material_id": material.id,
            "message": f"Material '{original_filename}' saved successfully."
        })
    except Exception as e:
        session.rollback()
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


@tool
def save_quiz(
    course_id: int,
    unit_id: int,
    title: str,
    description: Any = None,
    order_index: int = 1,
    time_limit_seconds: Any = None,
    passing_score: float = 70.0,
    max_attempts: int = 3,
) -> str:
    """
    Create a quiz container within a unit.

    A quiz is a container that holds multiple quiz questions. Each quiz
    is linked to a specific unit and can have multiple questions added to it.

    Args:
        course_id: The ID of the course
        unit_id: The ID of the unit this quiz belongs to
        title: Quiz title (e.g., "Unit 1 Quiz: Python Basics")
        description: What this quiz covers (e.g., "Covers content from Units 1-2")
        order_index: The order of this quiz within the unit (default: 1)
        time_limit_seconds: Time limit for the quiz (None = no limit)
        passing_score: Percentage needed to pass (0-100, default: 70)
        max_attempts: Maximum number of attempts allowed (default: 3)

    Returns:
        JSON string with quiz_id and status
    """
    session = get_db_session("constructor")

    try:
        # Sanitize optional parameters
        description_clean = _sanitize_value(description)
        time_limit_clean = _sanitize_optional_int(time_limit_seconds)

        quiz = Quiz(
            course_id=course_id,
            unit_id=unit_id,
            title=title,
            description=description_clean,
            order_index=order_index,
            time_limit_seconds=time_limit_clean,
            passing_score=passing_score,
            max_attempts=max_attempts,
            is_published=False,
        )
        session.add(quiz)
        session.commit()
        session.refresh(quiz)

        return json.dumps({
            "success": True,
            "quiz_id": quiz.id,
            "message": f"Quiz '{title}' created successfully."
        })
    except Exception as e:
        session.rollback()
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


@tool
def save_quiz_question(
    quiz_id: int,
    course_id: int,
    unit_id: int,
    question_text: str,
    question_type: str,
    options: Any = None,
    correct_answer: str = "",
    rubric: Any = None,
    difficulty: str = "medium",
    points_value: float = 1.0,
    order_index: int = 0,
    tags: Any = None,
) -> str:
    """
    Save a quiz question to a quiz.

    Creates a quiz question linked to a specific quiz. The quiz must exist first.

    Args:
        quiz_id: The ID of the quiz this question belongs to
        course_id: The ID of the course
        unit_id: The ID of the unit (for easier queries)
        question_text: The question text
        question_type: Type - "multiple_choice", "true_false", "short_answer", or "essay"
        options: JSON string of options for multiple choice: [{"text": "Option A", "is_correct": false}]
        correct_answer: The correct answer
        rubric: Grading criteria for open-ended questions
        difficulty: "easy", "medium", or "hard"
        points_value: Points this question is worth (default: 1.0)
        order_index: Order within the quiz (default: 0)
        tags: Optional list of tags for the question

    Returns:
        JSON string with question_id and status
    """
    session = get_db_session("constructor")

    try:
        # Sanitize optional parameters
        options_clean = _sanitize_value(options)
        rubric_clean = _sanitize_value(rubric)
        tags_clean = _sanitize_optional_list(tags)

        # Build metadata JSON
        metadata = {}
        if tags_clean:
            metadata["tags"] = tags_clean

        question = QuizQuestion(
            quiz_id=quiz_id,
            course_id=course_id,
            unit_id=unit_id,
            question_text=question_text,
            question_type=question_type,
            options=options_clean,  # Already a JSON string
            correct_answer=correct_answer,
            rubric=rubric_clean,
            difficulty=difficulty,
            points_value=points_value,
            order_index=order_index,
            course_metadata=metadata if metadata else None,
        )
        session.add(question)
        session.commit()
        session.refresh(question)

        return json.dumps({
            "success": True,
            "question_id": question.id,
            "message": f"Question saved successfully."
        })
    except Exception as e:
        session.rollback()
        return json.dumps({
            "success": False,
            "error": str(e)
        })
    finally:
        session.close()


@tool
def get_uploaded_files(creator_id: int, course_id: int) -> str:
    """
    Get the list of uploaded files for a creator's course.

    Files are organized by: uploads/constructor/{creator_id}/{course_id}/

    Args:
        creator_id: The ID of the creator (user)
        course_id: The ID of the course (always available since session start auto-creates the course)

    Returns:
        JSON string with list of uploaded files and their paths
    """
    from pathlib import Path
    from app.core.config import get_settings
    import os

    settings = get_settings()

    logger.info(f"[get_uploaded_files] creator_id={creator_id}, course_id={course_id}")

    # Base constructor directory
    constructor_base = settings.upload_absolute_path / "constructor" / str(creator_id)

    if not constructor_base.exists():
        result = {
            "success": True,
            "files": [],
            "upload_dir": str(constructor_base),
            "message": f"No upload directory found for creator {creator_id}"
        }
        return json.dumps(result)

    files = []

    # Look for files in the specific course folder (recursively)
    course_dir = constructor_base / str(course_id)
    logger.info(f"[get_uploaded_files] Looking in course_dir: {course_dir}")

    if course_dir.exists():
        # Use rglob to recursively find all files (handles any nested structure)
        for file_path in course_dir.rglob("*"):
            if file_path.is_file():
                files.append(_parse_file_info(file_path))

    logger.info(f"[get_uploaded_files] Found {len(files)} files: {[f['original_filename'] for f in files]}")

    result = {
        "success": True,
        "creator_id": creator_id,
        "course_id": course_id,
        "files": files,
        "total_files": len(files),
        "message": f"Found {len(files)} uploaded file(s) for creator {creator_id}, course {course_id}"
    }
    return json.dumps(result)


def _parse_file_info(file_path: Path) -> dict:
    """Helper to parse file information from a file path."""
    filename = file_path.name
    original_filename = filename
    file_id = filename.split("_")[0] if "_" in filename else filename[:36]

    parts = filename.split("_", 1)
    if len(parts) > 1 and len(parts[0]) == 36:
        original_filename = parts[1]

    file_ext = file_path.suffix.lower()
    return {
        "file_id": file_id,
        "original_filename": original_filename,
        "saved_filename": filename,
        "full_path": str(file_path.absolute()),
        "file_ext": file_ext[1:] if file_ext else "",
        "size": file_path.stat().st_size,
    }


@tool
def get_session_info(session_id: str) -> str:
    """
    Get session information including uploaded files.

    This provides context about the current construction session including
    any uploaded files that need to be processed.

    Args:
        session_id: The WebSocket session ID

    Returns:
        JSON string with session information and uploaded files
    """
    from app.api.constructor import get_constructor_session

    session = get_constructor_session(session_id)
    uploaded_files = session.get("uploaded_files", [])

    return json.dumps({
        "success": True,
        "session_id": session_id,
        "uploaded_files": uploaded_files,
        "total_files": len(uploaded_files),
        "message": f"Session has {len(uploaded_files)} uploaded file(s)."
    })
