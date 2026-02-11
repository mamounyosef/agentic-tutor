"""Tutor Agents - Adaptive learning session agents.

This package provides the Tutor workflow agents:
- Session Coordinator: Main agent that guides the learning session
- Explainer: Provides RAG-based explanations (mode within coordinator)
- Gap Analysis: Identifies knowledge gaps (mode within coordinator)
- Hard-coded Quiz Grading: Fast, cost-effective assessment

The Tutor uses a single LangGraph with conditional routing to different modes,
unlike the Constructor which uses separate sub-agent graphs.

Key features:
- Personalized explanations based on student context
- Adaptive difficulty based on mastery and sentiment
- Spaced repetition scheduling
- Hard-coded quiz grading for speed and cost efficiency
- Session persistence with checkpointers
"""

from .graph import (
    build_tutor_graph,
    continue_tutoring_session,
    send_message_to_tutor,
    start_tutoring_session,
    TutorGraph,
)
from .state import TutorState, create_initial_tutor_state

__all__ = [
    # Graph
    "build_tutor_graph",
    "TutorGraph",
    # State
    "TutorState",
    "create_initial_tutor_state",
    # Convenience functions
    "start_tutoring_session",
    "continue_tutoring_session",
    "send_message_to_tutor",
]
