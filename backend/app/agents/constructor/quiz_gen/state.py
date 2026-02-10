"""State definition for the Quiz Generation Agent.

The Quiz Generation Agent creates quiz questions for each topic
in the course structure.
"""

from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict


class TopicQuizSpec(TypedDict):
    """Specification for quiz generation per topic."""

    topic_id: Optional[int]
    topic_title: str
    target_question_count: int
    question_types: List[str]  # ["multiple_choice", "true_false", "short_answer"]
    difficulty_distribution: Dict[str, int]  # {"easy": 1, "medium": 2, "hard": 1}
    content_chunks: List[Dict[str, Any]]


class GeneratedQuestion(TypedDict):
    """A generated quiz question."""

    question_type: str  # "multiple_choice" | "true_false" | "short_answer"
    question_text: str
    options: Optional[List[Dict[str, Any]]]  # For multiple choice
    correct_answer: str
    explanation: Optional[str]
    difficulty: str
    topic_title: str
    rubric: Optional[Dict[str, Any]]  # For short answer grading


class TopicQuizResult(TypedDict):
    """Result of quiz generation for a topic."""

    topic_title: str
    topic_id: Optional[int]
    questions: List[GeneratedQuestion]
    total_questions: int
    questions_by_type: Dict[str, int]
    questions_by_difficulty: Dict[str, int]
    success: bool
    errors: List[str]


class QuizGenState(TypedDict):
    """
    State for the Quiz Generation Agent.

    This agent generates quiz questions for all topics in the course.
    """

    # Input
    course_id: str
    course_title: str
    topics: List[Dict[str, Any]]  # Topics from structure agent
    content_chunks: List[Dict[str, Any]]  # All content chunks

    # Configuration
    target_questions_per_topic: int
    question_types: List[str]  # ["multiple_choice", "true_false", "short_answer"]
    difficulty_levels: List[str]  # ["easy", "medium", "hard"]

    # Processing phase
    phase: str  # "plan" | "select_topic" | "generate_questions" | "validate_questions" | "create_rubrics" | "finalize"

    # Current topic being processed
    current_topic_index: int
    current_topic: Optional[Dict[str, Any]]

    # Generated questions
    topic_quizzes: List[TopicQuizResult]
    all_questions: List[GeneratedQuestion]
    total_questions_generated: int

    # Question distribution
    questions_by_type: Dict[str, int]
    questions_by_difficulty: Dict[str, int]

    # Validation results
    validation_errors: List[str]
    validation_warnings: List[str]

    # Rubrics
    rubrics: Dict[str, Dict[str, Any]]  # question_id -> rubric

    # Progress tracking
    topics_completed: int
    topics_total: int

    # Errors
    errors: List[str]

    # Status
    generation_complete: bool


def create_initial_quiz_gen_state(
    course_id: str,
    course_title: str,
    topics: List[Dict[str, Any]],
    content_chunks: List[Dict[str, Any]],
    target_questions_per_topic: int = 5,
) -> QuizGenState:
    """
    Create an initial Quiz Generation state.

    Args:
        course_id: ID of the course
        course_title: Title of the course
        topics: List of topics from structure agent
        content_chunks: All content chunks for reference
        target_questions_per_topic: Target number of questions per topic

    Returns:
        Initial QuizGenState
    """
    return QuizGenState(
        course_id=course_id,
        course_title=course_title,
        topics=topics,
        content_chunks=content_chunks,
        target_questions_per_topic=target_questions_per_topic,
        question_types=["multiple_choice", "true_false", "short_answer"],
        difficulty_levels=["easy", "medium", "hard"],
        phase="plan",
        current_topic_index=0,
        current_topic=None,
        topic_quizzes=[],
        all_questions=[],
        total_questions_generated=0,
        questions_by_type={},
        questions_by_difficulty={},
        validation_errors=[],
        validation_warnings=[],
        rubrics={},
        topics_completed=0,
        topics_total=len(topics),
        errors=[],
        generation_complete=False,
    )
