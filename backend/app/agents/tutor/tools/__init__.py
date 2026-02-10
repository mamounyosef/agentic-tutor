"""Tutor workflow tools.

This module provides LangChain tools for the Tutor Agents:
- RAG: Retrieval from course content and student history
- Mastery: Tracking and updating student mastery
- Assessment: Grading answers and generating feedback
- Session: Managing tutoring sessions
"""

from .rag import (
    retrieve_topic_content,
    semantic_search_course,
    get_topic_summary,
    search_student_qna_history,
    get_relevant_explanations,
    get_student_misconceptions,
    get_student_context,
    retrieve_for_explanation,
)

from .mastery import (
    get_mastery_snapshot,
    get_topic_mastery,
    update_mastery_score,
    record_quiz_attempt,
    identify_weak_topics,
    check_spaced_repetition,
    get_mastery_trend,
)

from .assessment import (
    get_quiz_question,
    get_quiz_questions_batch,
    grade_multiple_choice,
    grade_with_rubric,
    grade_answer,
    generate_feedback,
    identify_misconception_from_answer,
)

from .session import (
    start_tutor_session,
    end_tutor_session,
    log_interaction,
    log_student_feedback,
    update_session_progress,
    get_session_state,
    check_session_end_conditions,
    generate_session_summary,
)

__all__ = [
    # RAG tools
    "retrieve_topic_content",
    "semantic_search_course",
    "get_topic_summary",
    "search_student_qna_history",
    "get_relevant_explanations",
    "get_student_misconceptions",
    "get_student_context",
    "retrieve_for_explanation",

    # Mastery tools
    "get_mastery_snapshot",
    "get_topic_mastery",
    "update_mastery_score",
    "record_quiz_attempt",
    "identify_weak_topics",
    "check_spaced_repetition",
    "get_mastery_trend",

    # Assessment tools
    "get_quiz_question",
    "get_quiz_questions_batch",
    "grade_multiple_choice",
    "grade_with_rubric",
    "grade_answer",
    "generate_feedback",
    "identify_misconception_from_answer",

    # Session tools
    "start_tutor_session",
    "end_tutor_session",
    "log_interaction",
    "log_student_feedback",
    "update_session_progress",
    "get_session_state",
    "check_session_end_conditions",
    "generate_session_summary",
]
