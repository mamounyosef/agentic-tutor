"""Session Coordinator Graph for Tutor workflow.

This module defines the main LangGraph for the Session Coordinator,
which orchestrates the entire tutoring session workflow.
"""

import logging
from typing import Any, Dict, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.observability.langsmith import build_trace_config
from .nodes import (
    explainer_node,
    gap_analysis_node,
    grade_quiz_node,
    intake_node,
    quiz_node,
    route_after_explainer,
    route_after_quiz,
    route_by_action,
    summarize_node,
    welcome_node,
)
from .state import TutorState, create_initial_tutor_state

logger = logging.getLogger(__name__)


class TutorGraph:
    """
    Wrapper class for the Tutor Session Coordinator Graph.

    Provides a clean interface for interacting with the LangGraph.
    """

    def __init__(self, session_id: str, checkpointer: Optional[MemorySaver] = None):
        """
        Initialize the Tutor Graph.

        Args:
            session_id: Unique session identifier
            checkpointer: Optional checkpointer for persistence
        """
        self.session_id = session_id
        self.checkpointer = checkpointer or self._create_checkpointer()
        self.graph = self._build_graph()

    def _create_checkpointer(self) -> MemorySaver:
        """Create a memory checkpointer for session persistence."""
        return MemorySaver()

    def _build_graph(self) -> StateGraph:
        """Build the Tutor Session Coordinator graph."""
        # Create the graph with our state type
        graph = StateGraph(TutorState)

        # Add nodes
        graph.add_node("welcome", welcome_node)
        graph.add_node("intake", intake_node)
        graph.add_node("explainer", explainer_node)
        graph.add_node("gap_analysis", gap_analysis_node)
        graph.add_node("quiz", quiz_node)
        graph.add_node("grade_quiz", grade_quiz_node)
        graph.add_node("summarize", summarize_node)
        graph.add_node("end_turn", self._end_turn_node)

        # Set entry point
        graph.set_entry_point("welcome")

        # Add edges
        graph.add_edge("welcome", "intake")

        # Conditional routing based on action
        graph.add_conditional_edges(
            "intake",
            route_by_action,
            {
                "explainer": "explainer",
                "gap_analysis": "gap_analysis",
                "quiz": "quiz",
                "grade_quiz": "grade_quiz",
                "summarize": "summarize",
                "end_turn": "end_turn",
            },
        )

        # After explainer, decide what to do
        graph.add_conditional_edges(
            "explainer",
            route_after_explainer,
            {
                "quiz": "quiz",
                "intake": "intake",
            },
        )

        # After gap analysis, go back to intake
        graph.add_edge("gap_analysis", "intake")

        # Quiz flow
        graph.add_conditional_edges(
            "quiz",
            route_after_quiz,
            {
                "quiz": "quiz",
                "intake": "intake",
            },
        )

        # After grading, either more questions or back to intake
        graph.add_conditional_edges(
            "grade_quiz",
            route_after_quiz,
            {
                "quiz": "quiz",
                "intake": "intake",
            },
        )

        # Summarize ends the session
        graph.add_edge("summarize", END)
        graph.add_edge("end_turn", END)

        return graph.compile(checkpointer=self.checkpointer)

    async def _end_turn_node(self, state: TutorState) -> TutorState:
        """Terminate execution for the current user turn without ending the session."""
        return state

    async def invoke(
        self,
        state: TutorState,
        config: Optional[Dict[str, Any]] = None,
    ) -> TutorState:
        """
        Invoke the graph with the given state.

        Args:
            state: Current tutor state
            config: Optional configuration (e.g., thread_id)

        Returns:
            Updated state after graph execution
        """
        config = config or {"configurable": {"thread_id": self.session_id}}
        return await self.graph.ainvoke(state, config=config)

    async def stream(
        self,
        state: TutorState,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Stream responses from the graph.

        Args:
            state: Current tutor state
            config: Optional configuration

        Yields:
            State updates as they occur
        """
        config = config or {"configurable": {"thread_id": self.session_id}}
        async for event in self.graph.astream(state, config=config):
            yield event

    def get_state(self, config: Optional[Dict[str, Any]] = None) -> Optional[TutorState]:
        """
        Get the current state from the checkpointer.

        Args:
            config: Optional configuration

        Returns:
            Current state values or None if not found
        """
        config = config or {"configurable": {"thread_id": self.session_id}}
        try:
            snapshot = self.graph.get_state(config)
        except Exception:
            return None

        if snapshot is None:
            return None

        values = getattr(snapshot, "values", None)
        if values is None:
            return None
        return values

    async def update_state(
        self,
        state_update: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Update the current state in the checkpointer.

        Args:
            state_update: Dictionary with state updates
            config: Optional configuration
        """
        config = config or {"configurable": {"thread_id": self.session_id}}
        try:
            current_state = self.get_state(config)
            if current_state:
                updated_state = {**current_state, **state_update}
                self.graph.update_state(config, updated_state)
        except Exception as e:
            logger.error(f"Error updating state: {e}")


def build_tutor_graph(
    session_id: str,
    checkpointer: Optional[MemorySaver] = None,
) -> TutorGraph:
    """
    Build and return a Tutor Session Coordinator graph.

    This is the main factory function for creating Tutor instances.

    Args:
        session_id: Unique session identifier
        checkpointer: Optional checkpointer for persistence

    Returns:
        Compiled TutorGraph instance
    """
    return TutorGraph(session_id, checkpointer)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def start_tutoring_session(
    student_id: int,
    course_id: int,
    session_goal: Optional[str] = None,
) -> tuple[str, TutorGraph]:
    """
    Start a new tutoring session.

    Args:
        student_id: ID of the student
        course_id: ID of the course
        session_goal: Optional learning goal

    Returns:
        Tuple of (session_id, tutor_graph)
    """
    import time

    session_id = f"tutor_{student_id}_{course_id}_{int(time.time())}"

    initial_state = create_initial_tutor_state(
        session_id=session_id,
        student_id=student_id,
        course_id=course_id,
        session_goal=session_goal,
    )

    graph = build_tutor_graph(session_id)

    # Initialize the session by invoking the welcome node
    init_config = build_trace_config(
        thread_id=session_id,
        tags=["tutor", "session_start"],
        metadata={
            "session_id": session_id,
            "student_id": student_id,
            "course_id": course_id,
        },
    )
    await graph.invoke(initial_state, config=init_config)

    return session_id, graph


async def continue_tutoring_session(session_id: str) -> Optional[TutorGraph]:
    """
    Continue an existing tutoring session.

    Args:
        session_id: Existing session identifier

    Returns:
        TutorGraph instance or None if session not found
    """
    graph = build_tutor_graph(session_id)

    # Check if session exists
    state = graph.get_state()
    if state is None:
        return None

    return graph


async def send_message_to_tutor(
    session_id: str,
    message: str,
    student_id: int,
    course_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Send a message to an existing tutor session.

    Args:
        session_id: Session identifier
        message: Student's message
        student_id: Student ID
        course_id: Course ID

    Returns:
        Updated state or None if session not found
    """
    graph = await continue_tutoring_session(session_id)
    if graph is None:
        return None

    # Get current state
    current_state = graph.get_state()
    if current_state is None:
        current_state = create_initial_tutor_state(
            session_id=session_id,
            student_id=student_id,
            course_id=course_id,
        )

    # Add the message
    updated_messages = current_state.get("messages", []) + [{
        "role": "user",
        "content": message,
    }]

    # Invoke the graph
    new_state = await graph.invoke({
        **current_state,
        "messages": updated_messages,
    })

    return new_state
