"""Tutor API endpoints for student learning workflow."""

import logging
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, func

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from langchain_core.messages import HumanMessage

from app.core.config import Settings, get_settings
from app.db.constructor.models import Course, Unit, Topic
from app.db.tutor.models import Student, Enrollment, Mastery, TutorSession
from app.db.base import get_constructor_session, get_tutor_session
from app.api.auth import get_current_student
from app.api.websocket import manager

# Import Tutor agents
from app.agents.tutor.graph import (
    build_tutor_graph,
    continue_tutoring_session,
    start_tutoring_session,
)
from app.agents.tutor.state import TutorState, create_initial_tutor_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tutor", tags=["Tutor"])


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

class TutorSessionStart(BaseModel):
    """Start a new tutoring session."""
    course_id: int
    goal: str | None = None
    session_length: int | None = None  # in minutes


class TutorChatMessage(BaseModel):
    """Message to the tutor agent."""
    message: str


class QuizAnswer(BaseModel):
    """Submit an answer to a quiz question."""
    session_id: str
    question_id: int
    answer: str


class EnrollRequest(BaseModel):
    """Enroll in a course."""
    course_id: int


# ==============================================================================
# Session Management
# ==============================================================================

# In-memory session storage (in production, use Redis or similar)
_tutor_sessions: dict[str, "TutorGraph"] = {}


def get_tutor_session_graph(session_id: str) -> Optional["TutorGraph"]:
    """Get or create a tutor session graph."""
    if session_id not in _tutor_sessions:
        _tutor_sessions[session_id] = build_tutor_graph(session_id)
    return _tutor_sessions[session_id]


# ==============================================================================
# WebSocket Endpoint for Streaming
# ==============================================================================

@router.websocket("/session/ws/{session_id}")
async def tutor_websocket(
    websocket: WebSocket,
    session_id: str,
):
    """
    WebSocket endpoint for streaming Tutor Agent responses.

    This provides real-time, token-by-token streaming of agent responses.
    """
    await manager.connect(session_id, websocket)
    logger.info(f"Tutor WebSocket connected for session: {session_id}")

    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_json()

            message_type = data.get("type", "message")

            if message_type == "message":
                user_message = data.get("message", "")
                if not user_message:
                    continue

                student_id = data.get("student_id")
                course_id = data.get("course_id")

                if not student_id or not course_id:
                    await manager.send_error(
                        session_id,
                        "Missing student_id or course_id",
                    )
                    continue

                # Get or create the graph
                graph = get_tutor_session_graph(session_id)

                # Get current state or initialize
                try:
                    current_state = graph.get_state()
                    if current_state is None:
                        # Initialize new session
                        current_state = create_initial_tutor_state(
                            session_id=session_id,
                            student_id=student_id,
                            course_id=course_id,
                            session_goal=data.get("goal"),
                        )
                except Exception:
                    current_state = create_initial_tutor_state(
                        session_id=session_id,
                        student_id=student_id,
                        course_id=course_id,
                        session_goal=data.get("goal"),
                    )

                # Add user message to state
                messages = current_state.get("messages", [])
                messages.append(HumanMessage(content=user_message))

                # Stream the graph execution
                try:
                    await manager.send_status(
                        session_id,
                        "Thinking...",
                        phase="processing",
                    )

                    async for event in graph.stream(
                        {**current_state, "messages": messages},
                    ):
                        # Stream events to client
                        for node_name, node_output in event.items():
                            if node_output and isinstance(node_output, dict):
                                # Extract and send any AI messages
                                node_messages = node_output.get("messages", [])
                                for msg in node_messages:
                                    if hasattr(msg, "type") and msg.type == "ai":
                                        content = msg.content
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

                                # Send status updates
                                current_topic = node_output.get("current_topic")
                                if current_topic:
                                    await manager.send_status(
                                        session_id,
                                        f"Topic: {current_topic.get('title', 'Current topic')}",
                                        phase="learning",
                                    )

                                # Send quiz questions
                                if "quiz_question" in node_output:
                                    await manager.broadcast_to_session(
                                        session_id,
                                        {
                                            "type": "quiz",
                                            "question": node_output.get("quiz_question"),
                                        },
                                    )

                                # Send mastery updates
                                if "mastery_snapshot" in node_output:
                                    await manager.broadcast_to_session(
                                        session_id,
                                        {
                                            "type": "mastery_update",
                                            "mastery": node_output.get("mastery_snapshot"),
                                        },
                                    )

                except Exception as e:
                    logger.error(f"Error in tutor stream: {e}")
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
                student_id = data.get("student_id")
                course_id = data.get("course_id")
                goal = data.get("goal")

                if not student_id or not course_id:
                    await manager.send_error(
                        session_id,
                        "Missing student_id or course_id",
                    )
                    continue

                # Use the convenience function
                session_id_result, graph = await start_tutoring_session(
                    student_id=student_id,
                    course_id=course_id,
                    session_goal=goal,
                )

                # Get the welcome message from state
                state = graph.get_state()
                if state and state.get("messages"):
                    for msg in state.get("messages", []):
                        if hasattr(msg, "type") and msg.type == "ai":
                            await manager.send_token(
                                session_id,
                                msg.content,
                                is_first=True,
                                is_last=True,
                            )
                            break

                # Send mastery snapshot
                mastery_snapshot = state.get("mastery_snapshot", {})
                await manager.broadcast_to_session(
                    session_id,
                    {
                        "type": "session_started",
                        "session_id": session_id_result,
                        "mastery_snapshot": mastery_snapshot,
                    },
                )

            elif message_type == "quiz_answer":
                # Handle quiz answer submission
                question_id = data.get("question_id")
                answer = data.get("answer")

                # The quiz grading is handled in the graph
                # This message triggers the grade_quiz node
                graph = get_tutor_session_graph(session_id)

                # Get current state and add quiz answer
                current_state = graph.get_state()
                if current_state:
                    updated_state = {
                        **current_state,
                        "quiz_answer": answer,
                        "current_question_id": question_id,
                    }

                    # Invoke graph to grade
                    result = await graph.invoke(updated_state)

                    # Send grading result
                    await manager.broadcast_to_session(
                        session_id,
                        {
                            "type": "quiz_result",
                            "is_correct": result.get("last_answer_correct", False),
                            "feedback": result.get("last_feedback", ""),
                            "mastery_updated": result.get("mastery_updated", False),
                        },
                    )

    except WebSocketDisconnect:
        manager.disconnect(session_id)
        logger.info(f"Tutor WebSocket disconnected for session: {session_id}")
    except Exception as e:
        logger.error(f"Error in tutor WebSocket: {e}")
        manager.disconnect(session_id)


# ==============================================================================
# Course Discovery Endpoints
# ==============================================================================

@router.get("/courses")
async def list_courses(
    current_student: Student = Depends(get_current_student),
    settings: Settings = Depends(get_settings)
) -> list[dict[str, Any]]:
    """
    List available courses for a student to enroll in.

    Returns courses from the Constructor database (read-only access).
    """
    async with get_constructor_session() as session:
        result = await session.execute(
            select(Course).where(Course.is_published == True)
        )
        courses = result.scalars().all()

        return [
            {
                "id": course.id,
                "title": course.title,
                "description": course.description,
                "difficulty": course.difficulty,
                "created_at": course.created_at,
            }
            for course in courses
        ]


@router.get("/course/{course_id}")
async def get_course_details(
    course_id: int,
    current_student: Student = Depends(get_current_student),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Get detailed information about a course."""
    async with get_constructor_session() as session:
        result = await session.execute(
            select(Course).where(Course.id == course_id)
        )
        course = result.scalar_one_or_none()

        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )

        # Get units and topics
        units_result = await session.execute(
            select(Unit).where(Unit.course_id == course_id)
        )
        units = units_result.scalars().all()

        units_data = []
        for unit in units:
            topics_result = await session.execute(
                select(Topic).where(Topic.unit_id == unit.id)
            )
            topics = topics_result.scalars().all()

            units_data.append({
                "id": unit.id,
                "title": unit.title,
                "description": unit.description,
                "order_index": unit.order_index,
                "topics": [
                    {
                        "id": topic.id,
                        "title": topic.title,
                        "description": topic.description,
                        "order_index": topic.order_index,
                    }
                    for topic in topics
                ],
            })

        return {
            "id": course.id,
            "title": course.title,
            "description": course.description,
            "difficulty": course.difficulty,
            "units": units_data,
        }


@router.post("/enroll")
async def enroll_in_course(
    request: EnrollRequest,
    current_student: Student = Depends(get_current_student),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Enroll a student in a course."""
    # Check if course exists
    async with get_constructor_session() as session:
        course_result = await session.execute(
            select(Course).where(Course.id == request.course_id)
        )
        course = course_result.scalar_one_or_none()

        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found"
            )

    # Check if already enrolled
    async with get_tutor_session() as session:
        existing_result = await session.execute(
            select(Enrollment).where(
                Enrollment.student_id == current_student.id,
                Enrollment.course_id == request.course_id
            )
        )
        if existing_result.scalar_one_or_none():
            return {"status": "already_enrolled", "course_id": request.course_id}

        # Create enrollment
        enrollment = Enrollment(
            student_id=current_student.id,
            course_id=request.course_id,
            status="active",
        )
        session.add(enrollment)
        await session.commit()

        # Initialize mastery records for all topics
        async with get_constructor_session() as constructor_session:
            # Get all topics for this course
            units_result = await constructor_session.execute(
                select(Unit).where(Unit.course_id == request.course_id)
            )
            units = units_result.scalars().all()

            for unit in units:
                topics_result = await constructor_session.execute(
                    select(Topic).where(Topic.unit_id == unit.id)
                )
                topics = topics_result.scalars().all()

                for topic in topics:
                    # Create mastery record
                    mastery = Mastery(
                        student_id=current_student.id,
                        topic_id=topic.id,
                        score=0.0,
                        attempts_count=0,
                    )
                    session.add(mastery)

            await session.commit()

        return {
            "status": "enrolled",
            "course_id": request.course_id,
            "message": "Successfully enrolled in course!",
        }


# ==============================================================================
# Tutor Session Endpoints (REST)
# ==============================================================================

@router.post("/session/start", status_code=status.HTTP_201_CREATED)
async def start_tutor_session_endpoint(
    request: TutorSessionStart,
    current_student: Student = Depends(get_current_student),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Start a new tutoring session with the Tutor Agent.

    Initializes LangGraph session and loads mastery data.
    """
    # Check if student is enrolled
    async with get_tutor_session() as session:
        enrollment_result = await session.execute(
            select(Enrollment).where(
                Enrollment.student_id == current_student.id,
                Enrollment.course_id == request.course_id
            )
        )
        enrollment = enrollment_result.scalar_one_or_none()

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enrolled in this course"
            )

    # Start the session using the agent function
    session_id, graph = await start_tutoring_session(
        student_id=current_student.id,
        course_id=request.course_id,
        session_goal=request.goal,
    )

    # Get the state to extract welcome message and mastery
    state = graph.get_state()

    welcome_message = "Hello! Let's learn together. What would you like to focus on today?"
    mastery_snapshot = {}

    if state:
        mastery_snapshot = state.get("mastery_snapshot", {})
        messages = state.get("messages", [])
        for msg in messages:
            if hasattr(msg, "type") and msg.type == "ai":
                welcome_message = msg.content
                break

    return {
        "session_id": session_id,
        "student_id": current_student.id,
        "course_id": request.course_id,
        "message": welcome_message,
        "mastery_snapshot": mastery_snapshot,
        "session_goal": request.goal,
        "websocket_url": f"/api/v1/tutor/session/ws/{session_id}",
    }


@router.post("/session/chat")
async def tutor_chat(
    request: TutorChatMessage,
    session_id: str = Query(...),
    current_student: Student = Depends(get_current_student),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Send a message to the Tutor Agent and get a response.

    The Session Coordinator Agent will:
    1. Analyze the message
    2. Select next action (explain, quiz, etc.)
    3. Dispatch to appropriate mode
    4. Return response to student

    For streaming responses, use the WebSocket endpoint instead.
    """
    graph = get_tutor_session_graph(session_id)

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
        messages.append(HumanMessage(content=request.message))

        # Invoke graph
        result = await graph.invoke({**current_state, "messages": messages})

        # Extract AI response
        response = "I understand. Let me help you with that."
        messages = result.get("messages", [])
        for msg in messages:
            if hasattr(msg, "type") and msg.type == "ai":
                response = msg.content
                break

        return {
            "session_id": session_id,
            "response": response,
            "action_taken": result.get("next_action", "respond"),
            "current_topic": result.get("current_topic"),
            "mastery_updated": result.get("mastery_updated", False),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in tutor chat: {e}")
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


@router.get("/session/{session_id}")
async def get_session_status(
    session_id: str,
    current_student: Student = Depends(get_current_student),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Get the current status of a tutoring session."""
    graph = get_tutor_session_graph(session_id)

    try:
        state = graph.get_state()
        if state is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )

        return {
            "session_id": session_id,
            "status": "active",
            "student_id": state.get("student_id"),
            "course_id": state.get("course_id"),
            "topics_covered": state.get("topics_covered", []),
            "session_goal": state.get("session_goal"),
            "current_topic": state.get("current_topic"),
            "mastery_snapshot": state.get("mastery_snapshot", {}),
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


@router.post("/session/end")
async def end_tutor_session(
    session_id: str,
    current_student: Student = Depends(get_current_student),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    End a tutoring session and provide summary.

    Saves final mastery snapshot and session summary.
    """
    graph = get_tutor_session_graph(session_id)

    try:
        # Get final state
        state = graph.get_state()

        if state:
            # Trigger summarize node if not already done
            if state.get("session_status") != "ended":
                # Invoke with end_session flag
                result = await graph.invoke({**state, "end_session": True})
                state = result

            mastery_snapshot = state.get("mastery_snapshot", {})
            topics_covered = state.get("topics_covered", [])
            session_summary = state.get("session_summary", "")

            # Calculate mastery gained
            mastery_gained = {}
            for topic_id, score in mastery_snapshot.items():
                if score > 0:
                    mastery_gained[topic_id] = score

            return {
                "session_id": session_id,
                "status": "completed",
                "topics_covered": topics_covered,
                "mastery_gained": mastery_gained,
                "session_summary": session_summary,
                "next_steps": state.get("next_steps", []),
            }

        return {
            "session_id": session_id,
            "status": "not_found",
        }

    except Exception as e:
        logger.error(f"Error ending session: {e}")
        return {
            "session_id": session_id,
            "status": "error",
            "error": str(e),
        }


# ==============================================================================
# Mastery & Progress Endpoints
# ==============================================================================

@router.get("/student/{student_id}/progress/{course_id}")
async def get_student_progress(
    student_id: int,
    course_id: int,
    current_student: Student = Depends(get_current_student),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Get a student's overall progress in a course.
    """
    # Verify student is requesting their own progress
    if current_student.id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this progress"
        )

    async with get_tutor_session() as session:
        # Get enrollment
        enrollment_result = await session.execute(
            select(Enrollment).where(
                Enrollment.student_id == student_id,
                Enrollment.course_id == course_id
            )
        )
        enrollment = enrollment_result.scalar_one_or_none()

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Not enrolled in this course"
            )

        # Get all mastery records for this student/course
        mastery_result = await session.execute(
            select(Mastery).where(
                Mastery.student_id == student_id,
            )
        )
        all_mastery = mastery_result.scalars().all()

        mastery_by_topic = {
            m.topic_id: float(m.score)
            for m in all_mastery
        }

        # Calculate average mastery
        avg_mastery = sum(mastery_by_topic.values()) / len(mastery_by_topic) if mastery_by_topic else 0

        # Get completion percentage
        completion_percentage = float(enrollment.completion_percentage or 0)

        # Find topics with low mastery for recommendations
        weak_topics = [
            topic_id
            for topic_id, score in mastery_by_topic.items()
            if score < 0.7
        ]

        return {
            "student_id": student_id,
            "course_id": course_id,
            "completion_percentage": completion_percentage,
            "overall_mastery": avg_mastery,
            "mastery_by_topic": mastery_by_topic,
            "next_recommended_topics": weak_topics[:3],  # Top 3 weak topics
        }


@router.get("/student/{student_id}/mastery")
async def get_mastery_report(
    student_id: int,
    course_id: int,
    current_student: Student = Depends(get_current_student),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Get detailed mastery report for a student in a course.

    Identifies:
    - Strong topics (mastery > 0.8)
    - Weak topics (mastery < 0.7)
    - Topics due for spaced repetition
    """
    if current_student.id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )

    async with get_tutor_session() as session:
        mastery_result = await session.execute(
            select(Mastery).where(Mastery.student_id == student_id)
        )
        all_mastery = mastery_result.scalars().all()

        strong_topics = []
        weak_topics = []
        due_for_review = []

        # Get topic titles from constructor DB
        topic_titles = {}
        async with get_constructor_session() as constructor_session:
            for m in all_mastery:
                topic_result = await constructor_session.execute(
                    select(Topic).where(Topic.id == m.topic_id)
                )
                topic = topic_result.scalar_one_or_none()
                if topic:
                    topic_titles[m.topic_id] = topic.title

        # Categorize topics
        seven_days_ago = datetime.now() - timedelta(days=7)

        for m in all_mastery:
            topic_title = topic_titles.get(m.topic_id, f"Topic {m.topic_id}")
            score = float(m.score)

            topic_data = {
                "topic_id": m.topic_id,
                "title": topic_title,
                "mastery": score,
                "attempts": m.attempts_count,
            }

            if score > 0.8:
                strong_topics.append(topic_data)
            elif score < 0.7:
                weak_topics.append(topic_data)

            # Check if due for spaced repetition
            if m.last_updated:
                # Simple logic: if not updated in 7 days and mastery < 0.9
                if score < 0.9:
                    due_for_review.append(topic_data)

        overall_mastery = (
            sum(m.score for m in all_mastery) / len(all_mastery)
            if all_mastery else 0
        )

        return {
            "student_id": student_id,
            "course_id": course_id,
            "overall_mastery": float(overall_mastery),
            "strong_topics": strong_topics,
            "weak_topics": weak_topics,
            "due_for_review": due_for_review,
        }


@router.get("/student/{student_id}/gaps")
async def identify_knowledge_gaps(
    student_id: int,
    course_id: int,
    current_student: Student = Depends(get_current_student),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Identify knowledge gaps using the Gap Analysis Agent.

    Finds prerequisite topics that have low mastery.
    """
    if current_student.id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )

    # Get mastery data
    async with get_tutor_session() as session:
        mastery_result = await session.execute(
            select(Mastery).where(Mastery.student_id == student_id)
        )
        all_mastery = mastery_result.scalars().all()

        mastery_by_topic = {
            m.topic_id: float(m.score)
            for m in all_mastery
        }

    # Get topics with prerequisites from constructor DB
    async with get_constructor_session() as constructor_session:
        units_result = await constructor_session.execute(
            select(Unit).where(Unit.course_id == course_id)
        )
        units = units_result.scalars().all()

        gaps = []
        remedation_plan = []

        for unit in units:
            topics_result = await constructor_session.execute(
                select(Topic).where(Topic.unit_id == unit.id).order_by(Topic.order_index)
            )
            topics = topics_result.scalars().all()

            for topic in topics:
                score = mastery_by_topic.get(topic.id, 0)

                # Check if topic has low mastery
                if score < 0.7:
                    gaps.append({
                        "topic_id": topic.id,
                        "title": topic.title,
                        "current_mastery": score,
                        "unit": unit.title,
                    })
                    remedation_plan.append({
                        "action": "review",
                        "topic_id": topic.id,
                        "title": topic.title,
                        "reason": f"Low mastery ({score:.1%})",
                    })

                # Check prerequisites
                if topic.prerequisites:
                    for prereq_id in topic.prerequisites:
                        prereq_mastery = mastery_by_topic.get(prereq_id, 0)
                        if prereq_mastery < 0.8:
                            prereq_result = await constructor_session.execute(
                                select(Topic).where(Topic.id == prereq_id)
                            )
                            prereq_topic = prereq_result.scalar_one_or_none()

                            if prereq_topic:
                                gaps.append({
                                    "topic_id": prereq_id,
                                    "title": prereq_topic.title,
                                    "current_mastery": prereq_mastery,
                                    "is_prerequisite_for": topic.title,
                                })
                                remedation_plan.append({
                                    "action": "study_prerequisite",
                                    "topic_id": prereq_id,
                                    "title": prereq_topic.title,
                                    "required_for": topic.title,
                                    "reason": f"Prerequisite mastery low ({prereq_mastery:.1%})",
                                })

        return {
            "student_id": student_id,
            "course_id": course_id,
            "gaps": gaps,
            "remediation_plan": remedation_plan[:10],  # Top 10 priorities
        }


# ==============================================================================
# Quiz Endpoints
# ==============================================================================

@router.post("/quiz/answer")
async def submit_quiz_answer(
    request: QuizAnswer,
    current_student: Student = Depends(get_current_student),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Submit an answer to a quiz question for grading.

    Uses hard-coded grading (not LLM) for speed and cost efficiency.
    """
    from app.db.constructor.models import QuizQuestion

    # Get the question
    async with get_constructor_session() as session:
        question_result = await session.execute(
            select(QuizQuestion).where(QuizQuestion.id == request.question_id)
        )
        question = question_result.scalar_one_or_none()

        if not question:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found"
            )

    # Hard-coded grading based on question type
    is_correct = False
    feedback = ""

    if question.question_type == "multiple_choice":
        is_correct = request.answer.strip().lower() == question.correct_answer.strip().lower()
        feedback = "Correct!" if is_correct else f"The correct answer is: {question.correct_answer}"

    elif question.question_type == "true_false":
        is_correct = request.answer.strip().lower() == question.correct_answer.strip().lower()
        feedback = "Correct!" if is_correct else f"The correct answer is: {question.correct_answer}"

    elif question.question_type == "short_answer":
        # Simple fuzzy matching for short answers
        user_clean = request.answer.strip().lower()
        correct_clean = question.correct_answer.strip().lower()
        is_correct = user_clean == correct_clean or correct_clean in user_clean
        feedback = "Correct!" if is_correct else f"The correct answer is: {question.correct_answer}"

    # Update mastery
    new_mastery = 0.0
    mastery_updated = False

    async with get_tutor_session() as session:
        mastery_result = await session.execute(
            select(Mastery).where(
                Mastery.student_id == current_student.id,
                Mastery.topic_id == question.topic_id
            )
        )
        mastery = mastery_result.scalar_one_or_none()

        if mastery:
            # Moving average: new_score = 0.7 * old_score + 0.3 * performance
            performance = 1.0 if is_correct else 0.3
            old_score = float(mastery.score)
            new_mastery = 0.7 * old_score + 0.3 * performance

            mastery.score = new_mastery
            mastery.attempts_count += 1
            await session.commit()
            mastery_updated = True

    return {
        "question_id": request.question_id,
        "is_correct": is_correct,
        "score": 1.0 if is_correct else 0.0,
        "feedback": feedback,
        "mastery_updated": mastery_updated,
        "new_mastery": new_mastery,
    }


@router.get("/course/{course_id}/quiz/question")
async def get_quiz_question(
    course_id: int,
    topic_id: int | None = None,
    difficulty: str = "medium",
    current_student: Student = Depends(get_current_student),
    settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """
    Get a quiz question for a specific topic.

    Fetches from the Constructor database (read-only).
    """
    from app.db.constructor.models import QuizQuestion

    async with get_constructor_session() as session:
        query = select(QuizQuestion).where(QuizQuestion.course_id == course_id)

        if topic_id:
            query = query.where(QuizQuestion.topic_id == topic_id)

        if difficulty:
            query = query.where(QuizQuestion.difficulty == difficulty)

        result = await session.execute(query)
        questions = result.scalars().all()

        if not questions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No questions found for the given criteria"
            )

        # Randomly select one question
        question = random.choice(questions)

        return {
            "question_id": question.id,
            "topic_id": question.topic_id,
            "question_text": question.question_text,
            "question_type": question.question_type,
            "options": question.options if question.question_type == "multiple_choice" else None,
            "difficulty": question.difficulty,
        }


# Type alias for TutorGraph
from app.agents.tutor.graph import TutorGraph
