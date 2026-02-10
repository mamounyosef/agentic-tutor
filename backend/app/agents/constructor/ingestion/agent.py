"""Ingestion Agent Graph Definition."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from ....core.config import get_settings
from ..state import ConstructorState
from .nodes import (
    detect_file_types_node,
    extract_content_node,
    chunk_content_node,
    store_chunks_node,
    report_completion_node,
)

logger = logging.getLogger(__name__)


class IngestionGraph:
    """
    Ingestion Agent Graph.

    Processes uploaded files through a pipeline:
    1. Detect file types
    2. Extract content
    3. Chunk content
    4. Store in vector DB
    5. Report completion
    """

    def __init__(self, checkpointer: Optional[SqliteSaver] = None):
        """
        Initialize the Ingestion Graph.

        Args:
            checkpointer: Optional checkpointer for persistence
        """
        self.checkpointer = checkpointer
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the Ingestion Agent graph."""
        graph = StateGraph(ConstructorState)

        # Add nodes
        graph.add_node("detect_types", detect_file_types_node)
        graph.add_node("extract", extract_content_node)
        graph.add_node("chunk", chunk_content_node)
        graph.add_node("store", store_chunks_node)
        graph.add_node("report", report_completion_node)

        # Set entry point
        graph.set_entry_point("detect_types")

        # Linear pipeline
        graph.add_edge("detect_types", "extract")
        graph.add_edge("extract", "chunk")
        graph.add_edge("chunk", "store")
        graph.add_edge("store", "report")
        graph.add_edge("report", END)

        if self.checkpointer:
            return graph.compile(checkpointer=self.checkpointer)
        return graph.compile()

    async def invoke(
        self,
        state: ConstructorState,
        config: Optional[Dict[str, Any]] = None,
    ) -> ConstructorState:
        """
        Invoke the ingestion pipeline.

        Args:
            state: Current constructor state
            config: Optional configuration

        Returns:
            Updated state after processing
        """
        return await self.graph.ainvoke(state, config=config or {})


def build_ingestion_graph(
    checkpointer: Optional[SqliteSaver] = None,
) -> IngestionGraph:
    """
    Build and return an Ingestion Agent graph.

    Args:
        checkpointer: Optional checkpointer for persistence

    Returns:
        Compiled IngestionGraph instance
    """
    return IngestionGraph(checkpointer)
