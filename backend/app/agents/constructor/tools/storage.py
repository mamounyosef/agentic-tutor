"""Storage tools for persisting course data.

Tools for storing course records in MySQL and content in Vector DB.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Database Session Management
# =============================================================================

def get_constructor_db_session():
    """Get a database session for the Constructor database."""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        settings = get_settings()
        engine = create_engine(settings.CONSTRUCTOR_DB_URL)
        Session = sessionmaker(bind=engine)
        return Session()
    except Exception as e:
        logger.error(f"Error creating database session: {e}")
        return None


# =============================================================================
# Course Records
# =============================================================================

@tool
def create_course_record(
    creator_id: int,
    title: str,
    description: str,
    difficulty: str = "beginner",
) -> Dict[str, Any]:
    """
    Create a new course record in the database.

    Args:
        creator_id: ID of the course creator
        title: Course title
        description: Course description
        difficulty: Difficulty level (beginner, intermediate, advanced)

    Returns:
        Dictionary with course_id and status
    """
    session = get_constructor_db_session()
    if not session:
        return {
            "success": False,
            "error": "Could not connect to database",
            "course_id": None,
        }

    try:
        from sqlalchemy import text

        result = session.execute(
            text("""
                INSERT INTO courses (creator_id, title, description, difficulty, is_published)
                VALUES (:creator_id, :title, :description, :difficulty, FALSE)
            """),
            {
                "creator_id": creator_id,
                "title": title,
                "description": description,
                "difficulty": difficulty,
            },
        )
        session.commit()

        course_id = result.lastrowid

        return {
            "success": True,
            "course_id": course_id,
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating course record: {e}")
        return {
            "success": False,
            "error": str(e),
            "course_id": None,
        }
    finally:
        session.close()


@tool
def update_course_record(
    course_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    difficulty: Optional[str] = None,
    is_published: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Update an existing course record.

    Args:
        course_id: ID of the course to update
        title: New title (optional)
        description: New description (optional)
        difficulty: New difficulty level (optional)
        is_published: Publication status (optional)

    Returns:
        Dictionary with status
    """
    session = get_constructor_db_session()
    if not session:
        return {"success": False, "error": "Could not connect to database"}

    try:
        from sqlalchemy import text

        updates = []
        params = {"course_id": course_id}

        if title is not None:
            updates.append("title = :title")
            params["title"] = title
        if description is not None:
            updates.append("description = :description")
            params["description"] = description
        if difficulty is not None:
            updates.append("difficulty = :difficulty")
            params["difficulty"] = difficulty
        if is_published is not None:
            updates.append("is_published = :is_published")
            params["is_published"] = is_published

        if not updates:
            return {"success": True, "message": "No updates provided"}

        query = f"UPDATE courses SET {', '.join(updates)} WHERE id = :course_id"
        session.execute(text(query), params)
        session.commit()

        return {"success": True}

    except Exception as e:
        session.rollback()
        logger.error(f"Error updating course record: {e}")
        return {"success": False, "error": str(e)}
    finally:
        session.close()


# =============================================================================
# Unit Records
# =============================================================================

@tool
def create_unit_record(
    course_id: int,
    title: str,
    description: str,
    order_index: int,
) -> Dict[str, Any]:
    """
    Create a new unit record in the database.

    Args:
        course_id: ID of the course
        title: Unit title
        description: Unit description
        order_index: Order of the unit in the course

    Returns:
        Dictionary with unit_id and status
    """
    session = get_constructor_db_session()
    if not session:
        return {"success": False, "error": "Could not connect to database", "unit_id": None}

    try:
        from sqlalchemy import text

        result = session.execute(
            text("""
                INSERT INTO units (course_id, title, description, order_index)
                VALUES (:course_id, :title, :description, :order_index)
            """),
            {
                "course_id": course_id,
                "title": title,
                "description": description,
                "order_index": order_index,
            },
        )
        session.commit()

        unit_id = result.lastrowid

        return {
            "success": True,
            "unit_id": unit_id,
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating unit record: {e}")
        return {"success": False, "error": str(e), "unit_id": None}
    finally:
        session.close()


# =============================================================================
# Topic Records
# =============================================================================

@tool
def create_topic_record(
    unit_id: int,
    title: str,
    description: str,
    content_summary: str,
    order_index: int,
) -> Dict[str, Any]:
    """
    Create a new topic record in the database.

    Args:
        unit_id: ID of the unit
        title: Topic title
        description: Topic description
        content_summary: Summary of topic content
        order_index: Order of the topic in the unit

    Returns:
        Dictionary with topic_id and status
    """
    session = get_constructor_db_session()
    if not session:
        return {"success": False, "error": "Could not connect to database", "topic_id": None}

    try:
        from sqlalchemy import text

        result = session.execute(
            text("""
                INSERT INTO topics (unit_id, title, description, content_summary, order_index)
                VALUES (:unit_id, :title, :description, :content_summary, :order_index)
            """),
            {
                "unit_id": unit_id,
                "title": title,
                "description": description,
                "content_summary": content_summary,
                "order_index": order_index,
            },
        )
        session.commit()

        topic_id = result.lastrowid

        return {
            "success": True,
            "topic_id": topic_id,
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating topic record: {e}")
        return {"success": False, "error": str(e), "topic_id": None}
    finally:
        session.close()


# =============================================================================
# Material References
# =============================================================================

@tool
def save_material_reference(
    topic_id: int,
    file_path: str,
    file_type: str,
    original_filename: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Save a material reference to the database.

    Args:
        topic_id: ID of the topic the material belongs to
        file_path: Path where the file is stored
        file_type: Type of file (pdf, ppt, docx, video, text)
        original_filename: Original filename when uploaded
        metadata: Optional metadata about the file

    Returns:
        Dictionary with material_id and status
    """
    session = get_constructor_db_session()
    if not session:
        return {"success": False, "error": "Could not connect to database", "material_id": None}

    try:
        from sqlalchemy import text
        import json

        result = session.execute(
            text("""
                INSERT INTO materials (topic_id, material_type, file_path, original_filename, metadata)
                VALUES (:topic_id, :material_type, :file_path, :original_filename, :metadata)
            """),
            {
                "topic_id": topic_id,
                "material_type": file_type,
                "file_path": file_path,
                "original_filename": original_filename,
                "metadata": json.dumps(metadata or {}),
            },
        )
        session.commit()

        material_id = result.lastrowid

        return {
            "success": True,
            "material_id": material_id,
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error saving material reference: {e}")
        return {"success": False, "error": str(e), "material_id": None}
    finally:
        session.close()


# =============================================================================
# Quiz Question Storage
# =============================================================================

@tool
def save_quiz_question(
    topic_id: int,
    question_text: str,
    question_type: str,
    correct_answer: str,
    options: Optional[List[Dict[str, Any]]] = None,
    rubric: Optional[str] = None,
    difficulty: str = "medium",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Save a quiz question to the database.

    Args:
        topic_id: ID of the topic
        question_text: The question text
        question_type: Type of question (multiple_choice, true_false, short_answer)
        correct_answer: The correct answer
        options: Options for multiple choice questions
        rubric: Grading rubric for open-ended questions
        difficulty: Difficulty level (easy, medium, hard)
        metadata: Optional metadata

    Returns:
        Dictionary with question_id and status
    """
    session = get_constructor_db_session()
    if not session:
        return {"success": False, "error": "Could not connect to database", "question_id": None}

    try:
        from sqlalchemy import text
        import json

        result = session.execute(
            text("""
                INSERT INTO quiz_questions
                (topic_id, question_text, question_type, options, correct_answer, rubric, difficulty, metadata)
                VALUES
                (:topic_id, :question_text, :question_type, :options, :correct_answer, :rubric, :difficulty, :metadata)
            """),
            {
                "topic_id": topic_id,
                "question_text": question_text,
                "question_type": question_type,
                "options": json.dumps(options) if options else None,
                "correct_answer": correct_answer,
                "rubric": rubric,
                "difficulty": difficulty,
                "metadata": json.dumps(metadata) if metadata else None,
            },
        )
        session.commit()

        question_id = result.lastrowid

        return {
            "success": True,
            "question_id": question_id,
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error saving quiz question: {e}")
        return {"success": False, "error": str(e), "question_id": None}
    finally:
        session.close()


# =============================================================================
# Vector DB Storage
# =============================================================================

@tool
async def store_chunks_in_vector_db(
    course_id: int,
    chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Store content chunks in the vector database.

    Args:
        course_id: ID of the course
        chunks: List of chunks with 'text' and metadata

    Returns:
        Dictionary with chunk IDs and status
    """
    try:
        from app.vector.constructor_store import ConstructorVectorStore

        vector_store = ConstructorVectorStore(course_id)
        chunk_ids = await vector_store.add_content_chunks(chunks)

        return {
            "success": True,
            "chunk_ids": chunk_ids,
            "total_stored": len(chunk_ids),
        }

    except Exception as e:
        logger.error(f"Error storing chunks in vector DB: {e}")
        return {
            "success": False,
            "error": str(e),
            "chunk_ids": [],
        }


@tool
async def store_topic_in_vector_db(
    course_id: int,
    topic_id: int,
    title: str,
    summary: str,
    key_concepts: List[str],
) -> Dict[str, Any]:
    """
    Store a topic summary in the vector database.

    Args:
        course_id: ID of the course
        topic_id: ID of the topic
        title: Topic title
        summary: Topic summary
        key_concepts: List of key concepts

    Returns:
        Dictionary with status
    """
    try:
        from app.vector.constructor_store import ConstructorVectorStore

        vector_store = ConstructorVectorStore(course_id)

        topic_ids = await vector_store.add_topic_summaries([
            {
                "id": topic_id,
                "title": title,
                "summary": summary,
                "key_concepts": key_concepts,
            }
        ])

        return {
            "success": True,
            "topic_vector_id": topic_ids[0] if topic_ids else None,
        }

    except Exception as e:
        logger.error(f"Error storing topic in vector DB: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@tool
async def store_quiz_in_vector_db(
    course_id: int,
    question_id: int,
    question_text: str,
    topic_id: int,
    difficulty: str,
) -> Dict[str, Any]:
    """
    Store a quiz question in the vector database for similarity checking.

    Args:
        course_id: ID of the course
        question_id: ID of the question
        question_text: The question text
        topic_id: ID of the topic
        difficulty: Difficulty level

    Returns:
        Dictionary with status
    """
    try:
        from app.vector.constructor_store import ConstructorVectorStore

        vector_store = ConstructorVectorStore(course_id)

        question_ids = await vector_store.add_quiz_questions([
            {
                "id": question_id,
                "question_text": question_text,
                "topic_id": topic_id,
                "difficulty": difficulty,
            }
        ])

        return {
            "success": True,
            "question_vector_id": question_ids[0] if question_ids else None,
        }

    except Exception as e:
        logger.error(f"Error storing quiz in vector DB: {e}")
        return {
            "success": False,
            "error": str(e),
        }
