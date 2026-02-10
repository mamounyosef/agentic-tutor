"""Orchestration layer for Constructor sub-agents.

This module provides the integration between the Coordinator Agent
and its sub-agents (Ingestion, Structure, Quiz, Validation).
"""

import logging
from typing import Any, Dict, Optional

from langgraph.checkpoint.sqlite import SqliteSaver

from .ingestion import IngestionGraph
from .state import ConstructorState
from .structure import StructureGraph
from .quiz_gen import QuizGenGraph
from .validation import ValidationGraph

logger = logging.getLogger(__name__)


class ConstructorOrchestrator:
    """
    Orchestrates the interaction between Coordinator and sub-agents.

    This class provides a clean interface for the Coordinator to invoke
    sub-agents and integrate their results back into the main state.
    """

    def __init__(self, session_id: str, checkpointer: Optional[SqliteSaver] = None):
        """
        Initialize the orchestrator with all sub-agent graphs.

        Args:
            session_id: Unique session identifier
            checkpointer: Optional shared checkpointer
        """
        self.session_id = session_id
        self.checkpointer = checkpointer

        # Initialize sub-agent graphs
        self.ingestion_graph = IngestionGraph(checkpointer)
        self.structure_graph = StructureGraph(checkpointer)
        self.quiz_graph = QuizGenGraph(checkpointer)
        self.validation_graph = ValidationGraph(checkpointer)

    async def invoke_ingestion(self, state: ConstructorState) -> Dict[str, Any]:
        """
        Invoke the Ingestion Agent.

        Args:
            state: Current constructor state

        Returns:
            Updated state fields from ingestion
        """
        logger.info(f"Invoking Ingestion Agent for session {self.session_id}")

        # Prepare ingestion state from constructor state
        from .ingestion.state import IngestionState

        ingestion_state = IngestionState(
            course_id=state.get("course_id") or state.get("session_id"),
            uploaded_files=state.get("uploaded_files", []),
            processed_files=state.get("processed_files", []),
            extracted_contents=[],
            chunks_created=[],
            metadata_extracted={},
            errors=[],
            subagent_results=state.get("subagent_results", {}),
            content_chunks=state.get("content_chunks", []),
        )

        # Run ingestion graph
        result = await self.ingestion_graph.invoke(ingestion_state)

        # Extract results to return to coordinator
        return {
            "processed_files": result.get("processed_files", state.get("processed_files", [])),
            "content_chunks": result.get("content_chunks", state.get("content_chunks", [])),
            "subagent_results": {
                **state.get("subagent_results", {}),
                "ingestion": result.get("subagent_results", {}).get("ingestion", {}),
            },
            "progress": result.get("progress", state.get("progress", 0)),
            "errors": result.get("errors", []),
        }

    async def invoke_structure(self, state: ConstructorState) -> Dict[str, Any]:
        """
        Invoke the Structure Analysis Agent.

        Args:
            state: Current constructor state

        Returns:
            Updated state fields from structure analysis
        """
        logger.info(f"Invoking Structure Agent for session {self.session_id}")

        # Prepare structure state from constructor state
        from .structure.state import StructureState, create_initial_structure_state

        structure_state = create_initial_structure_state(
            course_id=state.get("course_id") or state.get("session_id"),
            course_title=state.get("course_info", {}).get("title", ""),
            content_chunks=state.get("content_chunks", []),
        )

        # Run structure graph
        result = await self.structure_graph.invoke(structure_state)

        # Extract structure hierarchy
        structure_hierarchy = result.get("structure_hierarchy", {})
        structure_for_db = result.get("structure_for_db", {})

        # Convert to units and topics format
        units = structure_for_db.get("units", [])
        topics = []
        for unit in units:
            topics.extend(unit.get("topics", []))

        return {
            "units": units,
            "topics": topics,
            "subagent_results": {
                **state.get("subagent_results", {}),
                "structure": {
                    "status": result.get("analysis_complete", False),
                    "units_count": len(units),
                    "topics_count": len(topics),
                    "quality_score": 1.0 - (0.1 * len(result.get("warnings", []))),
                },
            },
            "progress": 0.5,
            "errors": result.get("errors", []),
        }

    async def invoke_quiz(self, state: ConstructorState) -> Dict[str, Any]:
        """
        Invoke the Quiz Generation Agent.

        Args:
            state: Current constructor state

        Returns:
            Updated state fields from quiz generation
        """
        logger.info(f"Invoking Quiz Agent for session {self.session_id}")

        # Prepare quiz state from constructor state
        from .quiz_gen.state import QuizGenState, create_initial_quiz_gen_state

        # Convert topics to dict format
        topics_as_dict = [
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "description": t.get("description"),
                "unit_id": t.get("unit_id"),
                "order_index": t.get("order_index"),
            }
            for t in state.get("topics", [])
        ]

        quiz_state = create_initial_quiz_gen_state(
            course_id=state.get("course_id") or state.get("session_id"),
            course_title=state.get("course_info", {}).get("title", ""),
            topics=topics_as_dict,
            content_chunks=state.get("content_chunks", []),
        )

        # Run quiz graph
        result = await self.quiz_graph.invoke(quiz_state)

        # Extract quiz questions
        quiz_questions = result.get("quiz_questions_for_db", [])

        return {
            "quiz_questions": quiz_questions,
            "subagent_results": {
                **state.get("subagent_results", {}),
                "quiz": {
                    "status": "completed" if result.get("generation_complete") else "failed",
                    "total_questions": result.get("total_questions_generated", 0),
                    "questions_by_type": result.get("questions_by_type", {}),
                    "questions_by_difficulty": result.get("questions_by_difficulty", {}),
                },
            },
            "progress": 0.75,
            "errors": result.get("errors", []),
        }

    async def invoke_validation(self, state: ConstructorState) -> Dict[str, Any]:
        """
        Invoke the Validation Agent.

        Args:
            state: Current constructor state

        Returns:
            Updated state fields from validation
        """
        logger.info(f"Invoking Validation Agent for session {self.session_id}")

        # Prepare validation state from constructor state
        from .validation.state import ValidationState, create_initial_validation_state

        # Convert units and topics to dict format
        units_as_dict = [
            {
                "id": u.get("id"),
                "title": u.get("title"),
                "description": u.get("description"),
                "order_index": u.get("order_index"),
            }
            for u in state.get("units", [])
        ]

        topics_as_dict = [
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "description": t.get("description"),
                "unit_id": t.get("unit_id"),
                "order_index": t.get("order_index"),
            }
            for t in state.get("topics", [])
        ]

        # Build prerequisite map from topics
        prerequisite_map = {}
        for t in state.get("topics", []):
            topic_title = t.get("title", "")
            prereqs = t.get("prerequisites", [])
            if prereqs:
                # Convert prereq IDs to titles (simplified)
                prerequisite_map[topic_title] = [
                    state.get("topics", [{}])[i].get("title", "")
                    for i in prereqs
                    if i < len(state.get("topics", []))
                ]

        validation_state = create_initial_validation_state(
            course_id=state.get("course_id") or state.get("session_id"),
            course_title=state.get("course_info", {}).get("title", ""),
            units=units_as_dict,
            topics=topics_as_dict,
            content_chunks=state.get("content_chunks", []),
            quiz_questions=state.get("quiz_questions", []),
            prerequisite_map=prerequisite_map,
        )

        # Run validation graph
        result = await self.validation_graph.invoke(validation_state)

        final_result = result.get("final_result", {})

        return {
            "validation_passed": final_result.get("is_valid", False),
            "readiness_score": final_result.get("readiness_score", 0.0),
            "validation_errors": final_result.get("errors", []),
            "validation_warnings": final_result.get("warnings", []),
            "subagent_results": {
                **state.get("subagent_results", {}),
                "validation": {
                    "status": "passed" if final_result.get("is_valid") else "failed",
                    "readiness_score": final_result.get("readiness_score", 0.0),
                    "errors": final_result.get("errors", []),
                    "warnings": final_result.get("warnings", []),
                },
            },
            "progress": final_result.get("readiness_score", 0.0),
            "errors": result.get("errors", []),
        }


# Singleton instance per session
_orchestrators: Dict[str, ConstructorOrchestrator] = {}


def get_orchestrator(session_id: str, checkpointer: Optional[SqliteSaver] = None) -> ConstructorOrchestrator:
    """
    Get or create an orchestrator for the given session.

    Args:
        session_id: Unique session identifier
        checkpointer: Optional shared checkpointer

    Returns:
        ConstructorOrchestrator instance
    """
    if session_id not in _orchestrators:
        _orchestrators[session_id] = ConstructorOrchestrator(session_id, checkpointer)
    return _orchestrators[session_id]
