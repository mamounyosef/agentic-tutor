"""Orchestration layer for Constructor sub-agents.

This module provides the integration between the Coordinator Agent
and its sub-agents (Ingestion, Structure, Quiz, Validation).
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import delete

from app.agents.constructor.ingestion import IngestionGraph
from .state import ConstructorState
from app.agents.constructor.structure import StructureGraph
from app.agents.constructor.quiz_gen import QuizGenGraph
from app.agents.constructor.validation import ValidationGraph
from app.db.base import get_constructor_session
from app.db.constructor.models import QuizQuestion, Topic, Unit

logger = logging.getLogger(__name__)


class ConstructorOrchestrator:
    """
    Orchestrates the interaction between Coordinator and sub-agents.

    This class provides a clean interface for the Coordinator to invoke
    sub-agents and integrate their results back into the main state.
    """

    def __init__(self, session_id: str, checkpointer: Optional[MemorySaver] = None):
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

    @staticmethod
    def _as_positive_int(value: Any) -> Optional[int]:
        """Parse and validate positive integer IDs."""
        try:
            parsed = int(value)
            return parsed if parsed > 0 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_order_index(value: Any, fallback: int) -> int:
        """Normalize order index values from agent output."""
        try:
            parsed = int(value)
            return parsed if parsed >= 0 else fallback
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _normalize_title(value: Any, max_len: int = 255) -> str:
        """Normalize short title-like fields."""
        text = " ".join(str(value or "").split()).strip()
        return text[:max_len]

    @staticmethod
    def _normalize_text(value: Any) -> str:
        """Normalize free-form text fields."""
        return str(value or "").strip()

    @staticmethod
    def _normalize_question_type(value: Any) -> str:
        """Normalize question type to constructor DB enum values."""
        normalized = str(value or "").strip().lower()
        if normalized in {"multiple_choice", "true_false", "short_answer", "essay"}:
            return normalized
        return "multiple_choice"

    @staticmethod
    def _normalize_question_difficulty(value: Any) -> str:
        """Normalize difficulty to constructor DB enum values."""
        normalized = str(value or "").strip().lower()
        if normalized in {"easy", "medium", "hard"}:
            return normalized
        return "medium"

    @staticmethod
    def _normalize_options(value: Any) -> Optional[List[Dict[str, Any]]]:
        """Normalize MCQ options payload."""
        if isinstance(value, list):
            normalized: List[Dict[str, Any]] = []
            for option in value:
                if isinstance(option, dict):
                    normalized.append(option)
                else:
                    normalized.append({"text": str(option), "is_correct": False})
            return normalized
        return None

    @staticmethod
    def _normalize_rubric(value: Any) -> Optional[str]:
        """Normalize rubric payload to text."""
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        text = str(value).strip()
        return text if text else None

    def _hydrate_quiz_topic_ids(
        self,
        quiz_questions: List[Dict[str, Any]],
        topics: List[Dict[str, Any]],
        all_questions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Fill missing quiz topic IDs using topic title mappings."""
        topic_id_by_title: Dict[str, int] = {}
        for topic in topics:
            topic_id = self._as_positive_int(topic.get("id"))
            title_key = str(topic.get("title", "")).strip().lower()
            if topic_id and title_key:
                topic_id_by_title[title_key] = topic_id

        hydrated: List[Dict[str, Any]] = []
        for idx, question in enumerate(quiz_questions):
            item = dict(question)
            if self._as_positive_int(item.get("topic_id")) is None:
                topic_title = ""
                if idx < len(all_questions):
                    topic_title = str(all_questions[idx].get("topic_title", "")).strip().lower()
                mapped_topic_id = topic_id_by_title.get(topic_title)
                if mapped_topic_id:
                    item["topic_id"] = mapped_topic_id
            hydrated.append(item)

        return hydrated

    async def _persist_structure(
        self,
        course_id: int,
        units: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
        """Persist generated units/topics and return state-ready records."""
        persisted_units: List[Dict[str, Any]] = []
        persisted_topics: List[Dict[str, Any]] = []
        errors: List[str] = []

        if not units:
            return persisted_units, persisted_topics, errors

        async with get_constructor_session() as session:
            try:
                # Replace existing structure for deterministic reruns.
                await session.execute(delete(QuizQuestion).where(QuizQuestion.course_id == course_id))
                await session.execute(delete(Unit).where(Unit.course_id == course_id))
                await session.flush()

                sorted_units = sorted(
                    units,
                    key=lambda unit: self._safe_order_index(unit.get("order_index"), 0),
                )

                for unit_fallback_index, unit in enumerate(sorted_units):
                    unit_row = Unit(
                        course_id=course_id,
                        title=self._normalize_title(unit.get("title")),
                        description=self._normalize_text(unit.get("description")),
                        order_index=self._safe_order_index(unit.get("order_index"), unit_fallback_index),
                        prerequisites=unit.get("prerequisites") if isinstance(unit.get("prerequisites"), list) else None,
                    )
                    session.add(unit_row)
                    await session.flush()

                    persisted_unit_topics: List[Dict[str, Any]] = []
                    unit_topics = unit.get("topics", [])
                    sorted_topics = sorted(
                        unit_topics,
                        key=lambda topic: self._safe_order_index(topic.get("order_index"), 0),
                    )

                    for topic_fallback_index, topic in enumerate(sorted_topics):
                        topic_row = Topic(
                            unit_id=unit_row.id,
                            title=self._normalize_title(topic.get("title")),
                            description=self._normalize_text(topic.get("description")),
                            content_summary=self._normalize_text(topic.get("content_summary")),
                            order_index=self._safe_order_index(topic.get("order_index"), topic_fallback_index),
                        )
                        session.add(topic_row)
                        await session.flush()

                        persisted_topic = {
                            "id": topic_row.id,
                            "title": topic_row.title,
                            "description": topic_row.description,
                            "content_summary": topic_row.content_summary,
                            "prerequisites": topic.get("prerequisites", []),
                            "unit_id": unit_row.id,
                            "order_index": topic_row.order_index,
                        }
                        persisted_unit_topics.append(persisted_topic)
                        persisted_topics.append(persisted_topic)

                    persisted_units.append(
                        {
                            "id": unit_row.id,
                            "title": unit_row.title,
                            "description": unit_row.description,
                            "order_index": unit_row.order_index,
                            "topics": persisted_unit_topics,
                        }
                    )

                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.error("Failed to persist structure for course %s: %s", course_id, exc)
                errors.append(f"Failed to persist structure: {exc}")
                return [], [], errors

        return persisted_units, persisted_topics, errors

    async def _persist_quiz_questions(
        self,
        course_id: int,
        quiz_questions: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """Persist generated quiz questions and return state-ready records."""
        persisted_questions: List[Dict[str, Any]] = []
        errors: List[str] = []

        if not quiz_questions:
            return persisted_questions, errors

        async with get_constructor_session() as session:
            try:
                await session.execute(delete(QuizQuestion).where(QuizQuestion.course_id == course_id))
                await session.flush()

                for question in quiz_questions:
                    topic_id = self._as_positive_int(question.get("topic_id"))
                    if topic_id is None:
                        errors.append(
                            f"Skipped quiz question without topic_id: {str(question.get('question_text', ''))[:80]}"
                        )
                        continue

                    question_row = QuizQuestion(
                        topic_id=topic_id,
                        course_id=course_id,
                        question_text=self._normalize_text(question.get("question_text")),
                        question_type=self._normalize_question_type(question.get("question_type")),
                        options=self._normalize_options(question.get("options")),
                        correct_answer=self._normalize_text(question.get("correct_answer")),
                        rubric=self._normalize_rubric(question.get("rubric")),
                        difficulty=self._normalize_question_difficulty(question.get("difficulty")),
                    )
                    session.add(question_row)
                    await session.flush()

                    persisted_questions.append(
                        {
                            "id": question_row.id,
                            "topic_id": question_row.topic_id,
                            "question_text": question_row.question_text,
                            "question_type": question_row.question_type,
                            "options": question_row.options,
                            "correct_answer": question_row.correct_answer,
                            "difficulty": question_row.difficulty,
                            "rubric": question_row.rubric,
                        }
                    )

                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.error("Failed to persist quiz questions for course %s: %s", course_id, exc)
                errors.append(f"Failed to persist quiz questions: {exc}")
                return [], errors

        return persisted_questions, errors

    async def invoke_ingestion(self, state: ConstructorState) -> Dict[str, Any]:
        """
        Invoke the Ingestion Agent.

        Args:
            state: Current constructor state

        Returns:
            Updated state fields from ingestion
        """
        logger.info(f"Invoking Ingestion Agent for session {self.session_id}")

        # The ingestion graph is built on ConstructorState, not a separate
        # ingestion-specific state module.
        ingestion_state = {
            **state,
            "uploaded_files": state.get("uploaded_files", []),
            "processed_files": state.get("processed_files", []),
            "content_chunks": state.get("content_chunks", []),
            "subagent_results": state.get("subagent_results", {}),
            "errors": state.get("errors", []),
        }

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
        course_id = self._as_positive_int(state.get("course_id"))
        persistence_errors: List[str] = []

        persisted_units = units
        persisted_topics = topics
        if course_id:
            persisted_units, persisted_topics, persistence_errors = await self._persist_structure(course_id, units)
            if not persisted_units and units:
                # Keep in-memory results usable even if DB persistence fails.
                persisted_units = units
                persisted_topics = topics
        elif units:
            persistence_errors.append("Structure generated but not persisted because course_id is missing.")

        return {
            "units": persisted_units,
            "topics": persisted_topics,
            "messages": [
                {
                    "role": "assistant",
                    "content": (
                        f"Structure analysis complete: {len(persisted_units)} unit(s), "
                        f"{len(persisted_topics)} topic(s). "
                        + (
                            "I will continue with quiz generation next."
                            if persisted_topics
                            else "I couldn't derive strong topics from current content yet."
                        )
                    ),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ],
            "subagent_results": {
                **state.get("subagent_results", {}),
                "structure": {
                    "status": result.get("analysis_complete", False),
                    "units_count": len(persisted_units),
                    "topics_count": len(persisted_topics),
                    "persisted_to_db": bool(course_id and not persistence_errors),
                    "quality_score": 1.0 - (0.1 * len(result.get("warnings", []))),
                },
            },
            "progress": 0.5,
            "errors": [*result.get("errors", []), *persistence_errors],
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
        hydrated_quiz_questions = self._hydrate_quiz_topic_ids(
            quiz_questions=quiz_questions,
            topics=state.get("topics", []),
            all_questions=result.get("all_questions", []),
        )
        course_id = self._as_positive_int(state.get("course_id"))
        persistence_errors: List[str] = []

        persisted_questions = hydrated_quiz_questions
        if course_id:
            persisted_questions, persistence_errors = await self._persist_quiz_questions(
                course_id=course_id,
                quiz_questions=hydrated_quiz_questions,
            )
            if not persisted_questions and hydrated_quiz_questions:
                # Keep in-memory results usable even if DB persistence fails.
                persisted_questions = hydrated_quiz_questions
        elif hydrated_quiz_questions:
            persistence_errors.append("Quiz questions generated but not persisted because course_id is missing.")

        return {
            "quiz_questions": persisted_questions,
            "messages": [
                {
                    "role": "assistant",
                    "content": (
                        f"Quiz generation complete: {len(persisted_questions)} question(s) prepared. "
                        "Next step is course validation."
                    ),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ],
            "subagent_results": {
                **state.get("subagent_results", {}),
                "quiz": {
                    "status": "completed" if result.get("generation_complete") else "failed",
                    "total_questions": result.get("total_questions_generated", 0),
                    "persisted_questions": len(persisted_questions),
                    "persisted_to_db": bool(course_id and not persistence_errors),
                    "questions_by_type": result.get("questions_by_type", {}),
                    "questions_by_difficulty": result.get("questions_by_difficulty", {}),
                },
            },
            "progress": 0.75,
            "errors": [*result.get("errors", []), *persistence_errors],
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
        topics_by_id = {
            t.get("id"): t.get("title", "")
            for t in state.get("topics", [])
            if t.get("id") is not None
        }
        for t in state.get("topics", []):
            topic_title = t.get("title", "")
            prereqs = t.get("prerequisites", [])
            if prereqs:
                # Convert prerequisite topic IDs to titles.
                prerequisite_map[topic_title] = [
                    topics_by_id[prereq_id]
                    for prereq_id in prereqs
                    if prereq_id in topics_by_id
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
            "messages": [
                {
                    "role": "assistant",
                    "content": (
                        "Validation complete: "
                        f"readiness score {final_result.get('readiness_score', 0.0):.2f}. "
                        + (
                            "The course is ready to finalize."
                            if final_result.get("is_valid")
                            else "There are issues to address before finalization."
                        )
                    ),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ],
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


def get_orchestrator(session_id: str, checkpointer: Optional[MemorySaver] = None) -> ConstructorOrchestrator:
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
