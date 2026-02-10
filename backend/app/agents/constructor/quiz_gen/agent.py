"""Quiz Generation Agent Graph Definition.

This agent generates quiz questions for all topics in the course.
"""

import logging
from typing import Any, Dict, Optional

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from ....core.config import get_settings
from .nodes import (
    check_completion_node,
    create_rubrics_node,
    finalize_quiz_bank_node,
    generate_questions_node,
    plan_quiz_generation_node,
    select_next_topic_node,
    validate_questions_node,
)
from .state import QuizGenState, create_initial_quiz_gen_state

logger = logging.getLogger(__name__)


class QuizGenGraph:
    """
    Quiz Generation Agent Graph.

    Processes all topics through a pipeline:
    1. Plan quiz generation strategy
    2. Select next topic
    3. Generate questions for topic
    4. Validate questions
    5. Create rubrics for short answers
    6. Check if more topics remain
    7. Finalize quiz bank
    """

    def __init__(self, checkpointer: Optional[SqliteSaver] = None):
        """
        Initialize the Quiz Generation Graph.

        Args:
            checkpointer: Optional checkpointer for persistence
        """
        self.checkpointer = checkpointer
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the Quiz Generation Agent graph."""
        graph = StateGraph(QuizGenState)

        # Add nodes
        graph.add_node("plan_quiz_generation", plan_quiz_generation_node)
        graph.add_node("select_topic", select_next_topic_node)
        graph.add_node("generate_questions", generate_questions_node)
        graph.add_node("validate_questions", validate_questions_node)
        graph.add_node("create_rubrics", create_rubrics_node)
        graph.add_node("check_completion", check_completion_node)
        graph.add_node("finalize_quiz_bank", finalize_quiz_bank_node)

        # Set entry point
        graph.set_entry_point("plan_quiz_generation")

        # Main pipeline
        graph.add_edge("plan_quiz_generation", "select_topic")

        # Topic processing loop (with conditional routing)
        graph.add_conditional_edges(
            "select_topic",
            self._should_generate_or_end,
            {
                "generate": "generate_questions",
                "end": "finalize_quiz_bank",
            }
        )

        graph.add_edge("generate_questions", "validate_questions")
        graph.add_edge("validate_questions", "create_rubrics")
        graph.add_edge("create_rubrics", "check_completion")

        # Loop back or proceed
        graph.add_conditional_edges(
            "check_completion",
            self._should_continue_or_finalize,
            {
                "continue": "select_topic",
                "finalize": "finalize_quiz_bank",
            }
        )

        graph.add_edge("finalize_quiz_bank", END)

        if self.checkpointer:
            return graph.compile(checkpointer=self.checkpointer)
        return graph.compile()

    def _should_generate_or_end(self, state: QuizGenState) -> str:
        """Determine if we should generate questions or end."""
        if state.get("generation_complete", False):
            return "end"
        return "generate"

    def _should_continue_or_finalize(self, state: QuizGenState) -> str:
        """Determine if we should continue to next topic or finalize."""
        if state.get("generation_complete", False):
            return "finalize"
        return "continue"

    async def invoke(
        self,
        state: QuizGenState,
        config: Optional[Dict[str, Any]] = None,
    ) -> QuizGenState:
        """
        Invoke the quiz generation pipeline.

        Args:
            state: Current quiz generation state
            config: Optional configuration

        Returns:
            Updated state after processing
        """
        return await self.graph.ainvoke(state, config=config or {})


def build_quiz_gen_graph(
    checkpointer: Optional[SqliteSaver] = None,
) -> QuizGenGraph:
    """
    Build and return a Quiz Generation Agent graph.

    Args:
        checkpointer: Optional checkpointer for persistence

    Returns:
        Compiled QuizGenGraph instance
    """
    return QuizGenGraph(checkpointer)
