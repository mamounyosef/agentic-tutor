"""Structure Analysis Agent Graph Definition.

This agent analyzes ingested course content and organizes it into
a coherent structure with units, topics, and prerequisite relationships.
"""

import logging
from typing import Any, Dict, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.core.config import get_settings
from .nodes import (
    analyze_content_node,
    build_hierarchy_node,
    detect_topics_node,
    finalize_structure_node,
    group_into_units_node,
    identify_prerequisites_node,
    suggest_organization_node,
    validate_structure_node,
)
from .state import StructureState, create_initial_structure_state

logger = logging.getLogger(__name__)


class StructureGraph:
    """
    Structure Analysis Agent Graph.

    Processes ingested content through a pipeline:
    1. Analyze content
    2. Detect topics
    3. Group into units
    4. Identify prerequisites
    5. Build hierarchy
    6. Validate structure
    7. Suggest organization (await approval)
    8. Finalize structure
    """

    def __init__(self, checkpointer: Optional[MemorySaver] = None):
        """
        Initialize the Structure Analysis Graph.

        Args:
            checkpointer: Optional checkpointer for persistence
        """
        self.checkpointer = checkpointer
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the Structure Analysis Agent graph."""
        graph = StateGraph(StructureState)

        # Add nodes
        graph.add_node("analyze_content", analyze_content_node)
        graph.add_node("detect_topics", detect_topics_node)
        graph.add_node("group_into_units", group_into_units_node)
        graph.add_node("identify_prerequisites", identify_prerequisites_node)
        graph.add_node("build_hierarchy", build_hierarchy_node)
        graph.add_node("validate_structure", validate_structure_node)
        graph.add_node("suggest_organization", suggest_organization_node)
        graph.add_node("finalize_structure", finalize_structure_node)

        # Set entry point
        graph.set_entry_point("analyze_content")

        # Linear pipeline
        graph.add_edge("analyze_content", "detect_topics")
        graph.add_edge("detect_topics", "group_into_units")
        graph.add_edge("group_into_units", "identify_prerequisites")
        graph.add_edge("identify_prerequisites", "build_hierarchy")
        graph.add_edge("build_hierarchy", "validate_structure")
        graph.add_edge("validate_structure", "suggest_organization")
        graph.add_edge("suggest_organization", "finalize_structure")
        graph.add_edge("finalize_structure", END)

        if self.checkpointer:
            return graph.compile(checkpointer=self.checkpointer)
        return graph.compile()

    async def invoke(
        self,
        state: StructureState,
        config: Optional[Dict[str, Any]] = None,
    ) -> StructureState:
        """
        Invoke the structure analysis pipeline.

        Args:
            state: Current structure state
            config: Optional configuration

        Returns:
            Updated state after processing
        """
        return await self.graph.ainvoke(state, config=config or {})


def build_structure_graph(
    checkpointer: Optional[MemorySaver] = None,
) -> StructureGraph:
    """
    Build and return a Structure Analysis Agent graph.

    Args:
        checkpointer: Optional checkpointer for persistence

    Returns:
        Compiled StructureGraph instance
    """
    return StructureGraph(checkpointer)
