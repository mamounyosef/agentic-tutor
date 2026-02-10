"""Constructor Coordinator Agent Graph Definition.

This module defines the main LangGraph for the Coordinator Agent,
which orchestrates the entire course construction workflow.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from ....core.config import get_settings
from ..state import ConstructorState, create_initial_constructor_state
from .nodes import (
    welcome_node,
    intake_node,
    route_action_node,
    dispatch_node,
    respond_node,
    finalize_node,
    route_by_phase,
    should_continue,
    route_subagent,
)

logger = logging.getLogger(__name__)


class CoordinatorGraph:
    """
    Wrapper class for the Coordinator Agent Graph.

    Provides a clean interface for interacting with the LangGraph.
    """

    def __init__(self, session_id: str, checkpointer: Optional[SqliteSaver] = None):
        """
        Initialize the Coordinator Graph.

        Args:
            session_id: Unique session identifier
            checkpointer: Optional checkpointer for persistence
        """
        self.session_id = session_id
        self.checkpointer = checkpointer or self._create_checkpointer()
        self.graph = self._build_graph()

    def _create_checkpointer(self) -> SqliteSaver:
        """Create a SQLite checkpointer for session persistence."""
        settings = get_settings()
        checkpoint_dir = Path(settings.CONSTRUCTOR_CHECKPOINT_PATH)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        db_path = checkpoint_dir / f"session_{self.session_id}.db"
        return SqliteSaver.from_conn_string(str(db_path))

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

        # Sub-agent placeholder nodes (will be replaced with actual subgraphs)
        # For now, these just pass through to respond
        graph.add_node("ingestion", self._create_subagent_passthrough("ingestion"))
        graph.add_node("structure", self._create_subagent_passthrough("structure"))
        graph.add_node("quiz", self._create_subagent_passthrough("quiz"))
        graph.add_node("validation", self._create_subagent_passthrough("validation"))

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

    def _create_subagent_passthrough(self, agent_name: str):
        """Create a passthrough node for sub-agents (placeholder)."""
        async def passthrough(state: ConstructorState) -> Dict[str, Any]:
            logger.info(f"Sub-agent '{agent_name}' invoked (placeholder)")
            # Update state to indicate sub-agent completed
            return {
                "current_agent": "coordinator",
                "subagent_results": {
                    **state.get("subagent_results", {}),
                    agent_name: {"status": "completed", "message": f"{agent_name} processing complete"},
                },
            }
        return passthrough

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

    def get_state(self, config: Optional[Dict[str, Any]] = None) -> ConstructorState:
        """
        Get the current state from the checkpointer.

        Args:
            config: Optional configuration

        Returns:
            Current state or None if not found
        """
        config = config or {"configurable": {"thread_id": self.session_id}}
        return self.graph.get_state(config)


def build_coordinator_graph(
    session_id: str,
    checkpointer: Optional[SqliteSaver] = None,
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
