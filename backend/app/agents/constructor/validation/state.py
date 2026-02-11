"""State definition for the Validation Agent.

The Validation Agent checks course quality before publishing -
validates completeness, consistency, and readiness.
"""

from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict


class ContentValidationResult(TypedDict):
    """Result of content validation."""

    topics_without_content: List[str]
    content_coverage: Dict[str, float]  # topic_id -> coverage_score
    empty_topics: List[str]
    total_issues: int


class StructureValidationResult(TypedDict):
    """Result of structure validation."""

    circular_references: List[List[str]]  # prerequisite loops
    orphaned_topics: List[str]  # topics no one depends on
    unreachable_topics: List[str]  # topics that can't be reached
    hierarchy_issues: List[str]
    total_issues: int


class QuizValidationResult(TypedDict):
    """Result of quiz validation."""

    topics_without_quizzes: List[str]
    quiz_coverage: Dict[str, int]  # topic_id -> question_count
    difficulty_distribution: Dict[str, int]  # difficulty -> count
    unanswered_questions: List[str]
    total_issues: int


class ValidationResult(TypedDict):
    """Complete validation result."""

    is_valid: bool
    readiness_score: float  # 0.0 to 1.0
    errors: List[str]  # Critical issues that must be fixed
    warnings: List[str]  # Issues that should be addressed
    info: List[str]  # Informational messages

    content_validation: ContentValidationResult
    structure_validation: StructureValidationResult
    quiz_validation: QuizValidationResult

    recommendations: List[str]  # Suggestions for improvement


class ValidationState(TypedDict):
    """
    State for the Validation Agent.

    This agent runs LAST after all other agents complete.
    It validates the entire course for readiness to publish.
    """

    # Input
    course_id: str
    course_title: str
    units: List[Dict[str, Any]]  # From structure agent
    topics: List[Dict[str, Any]]  # From structure agent
    content_chunks: List[Dict[str, Any]]  # From ingestion agent
    quiz_questions: List[Dict[str, Any]]  # From quiz agent
    prerequisite_map: Dict[str, List[str]]  # From structure agent

    # Validation phase
    phase: str  # "validate_content" | "validate_structure" | "validate_quiz" | "calculate_readiness" | "generate_report"

    # Validation results
    content_validation: Optional[ContentValidationResult]
    structure_validation: Optional[StructureValidationResult]
    quiz_validation: Optional[QuizValidationResult]

    # Final result
    final_result: Optional[ValidationResult]

    # Status
    validation_complete: bool
    awaiting_fixes: bool

    # Errors
    errors: List[str]


def create_initial_validation_state(
    course_id: str,
    course_title: str,
    units: List[Dict[str, Any]],
    topics: List[Dict[str, Any]],
    content_chunks: List[Dict[str, Any]],
    quiz_questions: List[Dict[str, Any]],
    prerequisite_map: Dict[str, List[str]],
) -> ValidationState:
    """
    Create an initial Validation state.

    Args:
        course_id: ID of the course
        course_title: Title of the course
        units: Course units from structure agent
        topics: Course topics from structure agent
        content_chunks: Content chunks from ingestion agent
        quiz_questions: Quiz questions from quiz agent
        prerequisite_map: Prerequisite relationships from structure agent

    Returns:
        Initial ValidationState
    """
    return ValidationState(
        course_id=course_id,
        course_title=course_title,
        units=units,
        topics=topics,
        content_chunks=content_chunks,
        quiz_questions=quiz_questions,
        prerequisite_map=prerequisite_map,
        phase="validate_content",
        content_validation=None,
        structure_validation=None,
        quiz_validation=None,
        final_result=None,
        validation_complete=False,
        awaiting_fixes=False,
        errors=[],
    )
