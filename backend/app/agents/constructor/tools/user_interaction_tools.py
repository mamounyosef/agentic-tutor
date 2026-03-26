"""User interaction tools for the Constructor agent system.

These tools allow the agent to ask the user structured questions
that appear as modal popups in the frontend using LangGraph's interrupt mechanism.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from langgraph.types import interrupt

logger = logging.getLogger(__name__)


@tool
def ask_user(
    question: str,
    choices: List[str],
) -> str:
    """
    Ask the user a multiple-choice question (appears as popup modal).

    IMPORTANT: Agent execution will PAUSE when you call this tool.
    The user's answer will be returned directly - do NOT call any other tools to get the answer.

    Args:
        question (str): Your question text
        choices (list[str]): List of answer choices (2-4 options recommended). Frontend adds "Other" option automatically.

    Returns:
        str: The user's answer (either one of the choices or a custom "Other" response)

    Example:
        difficulty = ask_user("What difficulty level for this course?", ["Beginner", "Intermediate", "Advanced"])
        # Agent pauses here, modal shows, user clicks "Beginner"
        # difficulty now contains "Beginner"
        print(f"User selected: {difficulty}")
    """
    if not question or not question.strip():
        raise ValueError("Question cannot be empty")

    # Limit to reasonable number of choices
    choices = choices[:4]

    logger.info(f"ask_user: Asking question: {question}")
    logger.info(f"ask_user: Choices: {choices}")
    logger.info("ask_user: About to call interrupt()...")

    # Use LangGraph's interrupt() - execution pauses here until user responds
    # The payload is sent to frontend via __interrupt__ in the result
    user_answer = interrupt({
        "type": "question",
        "question": question,
        "choices": choices,
    })

    logger.info(f"ask_user: Resumed after interrupt! User answered: {user_answer}")
    return user_answer
