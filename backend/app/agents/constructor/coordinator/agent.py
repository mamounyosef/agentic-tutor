"""Constructor Coordinator Agent Graph Definition.

This module defines the main LangGraph for the Coordinator Agent,
which orchestrates the entire course construction workflow.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.core.config import get_settings
from app.agents.constructor.orchestration import ConstructorOrchestrator, get_orchestrator
from app.agents.constructor.state import ConstructorState, create_initial_constructor_state
from .nodes import (
    dispatch_node,
    finalize_node,
    intake_node,
    respond_node,
    route_action_node,
    route_by_phase,
    route_subagent,
    should_continue,
    welcome_node,
)

logger = logging.getLogger(__name__)


class CoordinatorGraph:
    """
    Wrapper class for the Coordinator Agent Graph.

    Provides a clean interface for interacting with the LangGraph.
    """

    def __init__(self, session_id: str, checkpointer: Optional[MemorySaver] = None):
        """
        Initialize the Coordinator Graph.

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
        """Build the Coordinator Agent graph."""
        # Create the graph with our state type
        graph = StateGraph(ConstructorState)

        # Add nodes
        graph.add_node("welcome", welcome_node)
        graph.add_node("intake", intake_node)
        graph.add_node("route_action", route_action_node)
        graph.add_node("dispatch", dispatch_node)
        graph.add_node("respond", respond_node)
        graph.add_node("finalize", finalize_node)

        # Sub-agent nodes (now with actual invocation)
        graph.add_node("ingestion", self._create_ingestion_node())
        graph.add_node("structure", self._create_structure_node())
        graph.add_node("quiz", self._create_quiz_node())
        graph.add_node("validation", self._create_validation_node())

        # Set entry point
        graph.set_entry_point("welcome")

        # Add edges
        graph.add_edge("welcome", "intake")
        graph.add_edge("intake", "route_action")

        # Conditional routing based on action
        graph.add_conditional_edges(
            "route_action",
            route_by_phase,
            {
                "intake": "intake",
                "respond": "respond",
                "dispatch": "dispatch",
                "finalize": "finalize",
            },
        )

        # Dispatch routes to sub-agents
        graph.add_conditional_edges(
            "dispatch",
            route_subagent,
            {
                "coordinator": "respond",
                "ingestion": "ingestion",
                "structure": "structure",
                "quiz": "quiz",
                "validation": "validation",
            },
        )

        # Sub-agents return to respond
        graph.add_edge("ingestion", "respond")
        graph.add_edge("structure", "respond")
        graph.add_edge("quiz", "respond")
        graph.add_edge("validation", "respond")

        # Check if we should continue
        graph.add_conditional_edges(
            "respond",
            should_continue,
            {
                "continue": "intake",
                "end": END,
            },
        )

        graph.add_edge("finalize", END)

        return graph.compile(checkpointer=self.checkpointer)

    def _create_ingestion_node(self):
        """Create the ingestion sub-agent node."""
        async def ingestion_node(state: ConstructorState) -> Dict[str, Any]:
            logger.info(f"Ingestion sub-agent invoked for session {self.session_id}")
            orchestrator = get_orchestrator(self.session_id, self.checkpointer)
            result = await orchestrator.invoke_ingestion(state)
            result["current_agent"] = "coordinator"
            return result
        return ingestion_node

    def _create_structure_node(self):
        """Create the structure sub-agent node."""
        async def structure_node(state: ConstructorState) -> Dict[str, Any]:
            logger.info(f"Structure sub-agent invoked for session {self.session_id}")
            orchestrator = get_orchestrator(self.session_id, self.checkpointer)
            result = await orchestrator.invoke_structure(state)
            result["current_agent"] = "coordinator"
            return result
        return structure_node

    def _create_quiz_node(self):
        """Create the quiz sub-agent node."""
        async def quiz_node(state: ConstructorState) -> Dict[str, Any]:
            logger.info(f"Quiz sub-agent invoked for session {self.session_id}")
            orchestrator = get_orchestrator(self.session_id, self.checkpointer)
            result = await orchestrator.invoke_quiz(state)
            result["current_agent"] = "coordinator"
            return result
        return quiz_node

    def _create_validation_node(self):
        """Create the validation sub-agent node."""
        async def validation_node(state: ConstructorState) -> Dict[str, Any]:
            logger.info(f"Validation sub-agent invoked for session {self.session_id}")
            orchestrator = get_orchestrator(self.session_id, self.checkpointer)
            result = await orchestrator.invoke_validation(state)
            result["current_agent"] = "coordinator"
            return result
        return validation_node

    async def invoke(
        self,
        state: ConstructorState,
        config: Optional[Dict[str, Any]] = None,
    ) -> ConstructorState:
        """
        Invoke the graph with the given state.

        Args:
            state: Current constructor state
            config: Optional configuration (e.g., thread_id)

        Returns:
            Updated state after graph execution
        """
        config = config or {"configurable": {"thread_id": self.session_id}}
        return await self.graph.ainvoke(state, config=config)

    async def stream(
        self,
        state: ConstructorState,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Stream responses from the graph.

        Args:
            state: Current constructor state
            config: Optional configuration

        Yields:
            State updates as they occur
        """
        config = config or {"configurable": {"thread_id": self.session_id}}
        async for event in self.graph.astream(state, config=config):
            yield event

    def get_state(self, config: Optional[Dict[str, Any]] = None) -> Optional[ConstructorState]:
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

        # LangGraph returns a StateSnapshot; API handlers expect dict-like state.
        values = getattr(snapshot, "values", None)
        if values is None:
            return None
        return values


def build_coordinator_graph(
    session_id: str,
    checkpointer: Optional[MemorySaver] = None,
) -> CoordinatorGraph:
    """
    Build and return a Coordinator Agent graph.

    This is the main factory function for creating Coordinator instances.

    Args:
        session_id: Unique session identifier
        checkpointer: Optional checkpointer for persistence

    Returns:
        Compiled CoordinatorGraph instance
    """
    return CoordinatorGraph(session_id, checkpointer)
