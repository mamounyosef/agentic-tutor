"""State definitions for the Tutor workflow.

This module defines the TypedDict classes used by all Tutor agents.
"""

from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

from langgraph.graph import add_messages
from typing_extensions import TypedDict


class TopicInfo(TypedDict):
    """Information about a learning topic."""

    id: int
    title: str
    description: str
    unit_id: Optional[int]
    order_index: int
    content_summary: Optional[str]
    prerequisites: List[int]


class UnitInfo(TypedDict):
    """Information about a course unit."""

    id: int
    title: str
    description: str
    order_index: int
    topics: List[TopicInfo]


class MasterySnapshot(TypedDict):
    """Student's mastery across topics."""

    topic_id: int
    score: float  # 0.0 to 1.0
    attempts_count: int
    last_updated: str
    streak_count: int


class QuizQuestion(TypedDict):
    """A quiz question."""

    id: int
    topic_id: int
    question_text: str
    question_type: str  # "multiple_choice" | "true_false" | "short_answer"
    options: Optional[List[Dict[str, Any]]]
    correct_answer: str
    difficulty: str  # "easy" | "medium" | "hard"


class GapInfo(TypedDict):
    """Information about a knowledge gap."""

    topic_id: int
    topic_title: str
    current_mastery: float
    required_mastery: float
    priority: str  # "critical" | "high" | "medium" | "low"
    is_prerequisite_for: List[int]  # Topic IDs that depend on this


class StudentContext(TypedDict):
    """Context about the student for personalization."""

    student_id: int
    course_id: int
    learning_style: Optional[Dict[str, Any]]
    sentiment_summary: Dict[str, Any]
    recent_feedback: List[Dict[str, Any]]
    recent_interactions: List[Dict[str, Any]]
    misconceptions: List[Dict[str, Any]]


class TutorState(TypedDict):
    """
    Complete state for the Tutor workflow.

    This state is managed by the Session Coordinator and passed between modes.
    """

    # Conversation history
    messages: Annotated[List[Dict[str, Any]], add_messages]

    # Session identification
    session_id: str
    student_id: int
    course_id: int

    # Current learning state
    current_topic: Optional[TopicInfo]
    current_unit: Optional[UnitInfo]
    mastery_snapshot: Dict[int, float]  # topic_id -> mastery score

    # Session goal and progress
    session_goal: Optional[str]
    topics_covered: List[int]  # topic_ids covered in this session
    interactions_count: int

    # Decision state
    current_mode: str  # "welcome" | "explainer" | "gap_analysis" | "quiz" | "review" | "end"
    next_action: str
    action_rationale: str

    # Student context (cached)
    student_context: Optional[StudentContext]

    # Knowledge gaps
    identified_gaps: List[GapInfo]
    weak_topics: List[int]  # topic_ids with mastery < threshold

    # Spaced repetition
    topics_due_for_review: List[int]  # topic_ids due for spaced repetition

    # Quiz state (hard-coded assessment, no LLM)
    current_quiz: Optional[Dict[str, Any]]
    quiz_position: int
    quiz_score: float
    quiz_start_time: Optional[str]
    quiz_completed: bool

    # Explanation state
    explanation_given: Optional[str]
    examples_used: List[str]

    # Navigation state (for auto-navigation or manual tracking)
    current_content_position: Optional[str]  # e.g., "video_123", "topic_45"
    content_progress: Dict[str, float]  # content_id -> progress (0-1)

    # Session control
    should_end: bool
    end_reason: Optional[str]
    session_summary: Optional[str]

    # Timestamps
    session_started_at: str
    last_activity_at: str

    # Error handling
    errors: List[str]


def create_initial_tutor_state(
    session_id: str,
    student_id: int,
    course_id: int,
    session_goal: Optional[str] = None,
) -> TutorState:
    """
    Create an initial Tutor state.

    Args:
        session_id: Unique session identifier
        student_id: ID of the student
        course_id: ID of the course
        session_goal: Optional learning goal for this session

    Returns:
        Initial TutorState
    """
    now = datetime.utcnow().isoformat()

    return TutorState(
        messages=[],
        session_id=session_id,
        student_id=student_id,
        course_id=course_id,
        current_topic=None,
        current_unit=None,
        mastery_snapshot={},
        session_goal=session_goal,
        topics_covered=[],
        interactions_count=0,
        current_mode="welcome",
        next_action="greet",
        action_rationale="Starting new session",
        student_context=None,
        identified_gaps=[],
        weak_topics=[],
        topics_due_for_review=[],
        current_quiz=None,
        quiz_position=0,
        quiz_score=0.0,
        quiz_start_time=None,
        quiz_completed=False,
        explanation_given=None,
        examples_used=[],
        current_content_position=None,
        content_progress={},
        should_end=False,
        end_reason=None,
        session_summary=None,
        session_started_at=now,
        last_activity_at=now,
        errors=[],
    )
