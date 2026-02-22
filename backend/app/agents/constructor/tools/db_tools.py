"""Database persistence tools for the Constructor agent system.

These tools allow sub-agents to save course data directly to the database.
"""

import json
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from app.db.base import get_constructor_session
from app.db.constructor.models import Course, Module, Unit, Material, QuizQuestion


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
    async def _create_course():
        async with get_constructor_session() as session:
            course = Course(
                creator_id=creator_id,
                title=title,
                description=description,
                difficulty=difficulty,
                is_published=False,
            )
            session.add(course)
            await session.commit()
            await session.refresh(course)
            return {
                "success": True,
                "course_id": course.id,
                "message": f"Course '{title}' created successfully."
            }

    import asyncio
    result = asyncio.run(_create_course())
    return json.dumps(result)


@tool
def save_module(
    course_id: int,
    title: str,
    description: str,
    order_index: int,
    prerequisites: Optional[List[int]] = None,
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
        prerequisites: List of module IDs that must be completed first

    Returns:
        JSON string with module_id and status
    """
    async def _save_module():
        async with get_constructor_session() as session:
            module = Module(
                course_id=course_id,
                title=title,
                description=description,
                order_index=order_index,
                prerequisites=prerequisites,
            )
            session.add(module)
            await session.commit()
            await session.refresh(module)
            return {
                "success": True,
                "module_id": module.id,
                "message": f"Module '{title}' saved successfully."
            }

    import asyncio
    result = asyncio.run(_save_module())
    return json.dumps(result)


@tool
def save_unit(
    module_id: int,
    title: str,
    description: str,
    order_index: int,
    prerequisites: Optional[List[int]] = None,
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
        prerequisites: List of unit IDs that must be completed first

    Returns:
        JSON string with unit_id and status
    """
    async def _save_unit():
        async with get_constructor_session() as session:
            unit = Unit(
                module_id=module_id,
                title=title,
                description=description,
                order_index=order_index,
                prerequisites=prerequisites,
            )
            session.add(unit)
            await session.commit()
            await session.refresh(unit)
            return {
                "success": True,
                "unit_id": unit.id,
                "message": f"Unit '{title}' saved successfully."
            }

    import asyncio
    result = asyncio.run(_save_unit())
    return json.dumps(result)


@tool
def save_material(
    course_id: int,
    unit_id: int,
    material_type: str,
    file_path: str,
    original_filename: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    page_count: Optional[int] = None,
) -> str:
    """
    Save a material (video, PDF, slides, etc.) to a unit.

    This stores the file path so the frontend can display the content
    to students. The actual file is stored on disk.

    Args:
        course_id: The ID of the course
        unit_id: The ID of the unit this material belongs to
        material_type: Type - "video", "pdf", "ppt", "pptx", "docx", "text", or "other"
        file_path: Full path to the stored file on disk
        original_filename: Original name of the uploaded file
        title: Optional title for the material
        description: Optional description of the material content
        duration_seconds: For videos - duration in seconds
        page_count: For PDFs/slides - number of pages

    Returns:
        JSON string with material_id and status
    """
    async def _save_material():
        async with get_constructor_session() as session:
            # Build metadata JSON
            metadata = {}
            if title:
                metadata["title"] = title
            if description:
                metadata["description"] = description
            if duration_seconds:
                metadata["duration_seconds"] = duration_seconds
            if page_count:
                metadata["page_count"] = page_count

            material = Material(
                course_id=course_id,
                unit_id=unit_id,
                material_type=material_type,
                file_path=file_path,
                original_filename=original_filename,
                course_metadata=metadata if metadata else None,
                processing_status="completed",
                chunks_count=0,
            )
            session.add(material)
            await session.commit()
            await session.refresh(material)
            return {
                "success": True,
                "material_id": material.id,
                "message": f"Material '{original_filename}' saved successfully."
            }

    import asyncio
    result = asyncio.run(_save_material())
    return json.dumps(result)


@tool
def save_quiz_question(
    course_id: int,
    unit_id: int,
    question_text: str,
    question_type: str,
    options: Optional[str] = None,
    correct_answer: str = "",
    rubric: Optional[str] = None,
    difficulty: str = "medium",
    tags: Optional[List[str]] = None,
) -> str:
    """
    Save a quiz question to the database.

    Creates a quiz question linked to a specific unit and course.

    Args:
        course_id: The ID of the course
        unit_id: The ID of the unit this question is for
        question_text: The question text
        question_type: Type - "multiple_choice", "true_false", "short_answer", or "essay"
        options: JSON string of options for multiple choice: [{"text": "Option A", "is_correct": false}]
        correct_answer: The correct answer
        rubric: Grading criteria for open-ended questions
        difficulty: "easy", "medium", or "hard"
        tags: Optional list of tags for the question

    Returns:
        JSON string with question_id and status
    """
    async def _save_question():
        async with get_constructor_session() as session:
            # Build metadata JSON
            metadata = {}
            if tags:
                metadata["tags"] = tags

            question = QuizQuestion(
                course_id=course_id,
                unit_id=unit_id,
                question_text=question_text,
                question_type=question_type,
                options=options,  # Already a JSON string
                correct_answer=correct_answer,
                rubric=rubric,
                difficulty=difficulty,
                course_metadata=metadata if metadata else None,
            )
            session.add(question)
            await session.commit()
            await session.refresh(question)
            return {
                "success": True,
                "question_id": question.id,
                "message": f"Question saved successfully."
            }

    import asyncio
    result = asyncio.run(_save_question())
    return json.dumps(result)
