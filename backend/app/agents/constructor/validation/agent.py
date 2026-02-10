"""Validation Agent Graph Definition.

This agent validates the course quality before publishing.
"""

import logging
from typing import Any, Dict, Optional

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from ....core.config import get_settings
from .nodes import (
    calculate_readiness_node,
    generate_report_node,
    validate_content_node,
    validate_quiz_node,
    validate_structure_node,
)
from .state import ValidationState, create_initial_validation_state

logger = logging.getLogger(__name__)


class ValidationGraph:
    """
    Validation Agent Graph.

    Validates the complete course through a pipeline:
    1. Validate content completeness
    2. Validate structure integrity
    3. Validate quiz coverage
    4. Calculate readiness score
    5. Generate validation report
    """

    def __init__(self, checkpointer: Optional[SqliteSaver] = None):
        """
        Initialize the Validation Graph.

        Args:
            checkpointer: Optional checkpointer for persistence
        """
        self.checkpointer = checkpointer
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the Validation Agent graph."""
        graph = StateGraph(ValidationState)

        # Add nodes
        graph.add_node("validate_content", validate_content_node)
        graph.add_node("validate_structure", validate_structure_node)
        graph.add_node("validate_quiz", validate_quiz_node)
        graph.add_node("calculate_readiness", calculate_readiness_node)
        graph.add_node("generate_report", generate_report_node)

        # Set entry point
        graph.set_entry_point("validate_content")

        # Linear pipeline
        graph.add_edge("validate_content", "validate_structure")
        graph.add_edge("validate_structure", "validate_quiz")
        graph.add_edge("validate_quiz", "calculate_readiness")
        graph.add_edge("calculate_readiness", "generate_report")
        graph.add_edge("generate_report", END)

        if self.checkpointer:
            return graph.compile(checkpointer=self.checkpointer)
        return graph.compile()

    async def invoke(
        self,
        state: ValidationState,
        config: Optional[Dict[str, Any]] = None,
    ) -> ValidationState:
        """
        Invoke the validation pipeline.

        Args:
            state: Current validation state
            config: Optional configuration

        Returns:
            Updated state after processing
        """
        return await self.graph.ainvoke(state, config=config or {})


def build_validation_graph(
    checkpointer: Optional[SqliteSaver] = None,
) -> ValidationGraph:
    """
    Build and return a Validation Agent graph.

    Args:
        checkpointer: Optional checkpointer for persistence

    Returns:
        Compiled ValidationGraph instance
    """
    return ValidationGraph(checkpointer)
