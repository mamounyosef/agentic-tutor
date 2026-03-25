"""User interaction tools for the Constructor agent system.

These tools allow the agent to ask the user structured questions
that appear as modal popups in the frontend.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# Store for pending questions (question_id -> question data)
# In production, this would be stored in Redis or a database
_pending_questions: Dict[str, Dict[str, Any]] = {}
_question_counter = 0


def _generate_question_id() -> str:
    """Generate a unique question ID."""
    global _question_counter
    _question_counter += 1
    return f"q_{_question_counter}_{id(object())}"


def get_pending_question(question_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a pending question by ID."""
    return _pending_questions.get(question_id)


def remove_pending_question(question_id: str) -> None:
    """Remove a pending question after it's been answered."""
    _pending_questions.pop(question_id, None)


@tool
def ask_user(
    question: str,
    choices: List[str],
) -> str:
    """
    Ask the user a multiple-choice question (appears as popup modal).

    Args:
        question (str): Your question text
        choices (list[str]): 0-3 options to show (preferably 3). Frontend always adds "Other" option for custom input.

    Returns:
        str: JSON string with question_id. User's response comes back automatically.

    Example:
        ask_user("What difficulty level?", ["Beginner", "Intermediate", "Advanced"])
    """
    if not question or not question.strip():
        return json.dumps({"success": False, "error": "Question cannot be empty"})

    # Limit to 3 choices
    choices = choices[:3]

    question_id = _generate_question_id()
    question_data = {
        "question_id": question_id,
        "question": question,
        "choices": choices,
        "status": "pending",
    }
    _pending_questions[question_id] = question_data

    logger.info(f"ask_user: Created question {question_id}: {question}")

    return json.dumps({
        "success": True,
        "question_id": question_id,
        "status": "pending",
        "message": "Question sent to user. Waiting for response.",
    })


@tool
def get_user_answer(question_id: str) -> str:
    """
    Check if a user has responded to a pending question.

    Use this to poll for the user's response after calling ask_user.

    Args:
        question_id: The ID returned by ask_user

    Returns:
        JSON string with the user's answer if available, or status="pending"
    """
    question_data = _pending_questions.get(question_id)

    if not question_data:
        return json.dumps({
            "success": False,
            "error": f"Question {question_id} not found or already answered"
        })

    if question_data.get("status") == "answered":
        # Remove from pending and return the answer
        answer = question_data.get("answer")
        remove_pending_question(question_id)
        return json.dumps({
            "success": True,
            "question_id": question_id,
            "status": "answered",
            "answer": answer,
            "answer_type": question_data.get("answer_type", "choice"),
        })

    return json.dumps({
        "success": True,
        "question_id": question_id,
        "status": "pending",
        "message": "Waiting for user response..."
    })


def submit_user_answer(question_id: str, answer: str, answer_type: str = "choice") -> bool:
    """
    Submit a user's answer to a pending question.

    This is called by the WebSocket handler when the user responds.

    Args:
        question_id: The ID of the question
        answer: The user's answer text
        answer_type: Either "choice" (selected from options) or "other" (custom input)

    Returns:
        True if the answer was recorded, False if question not found
    """
    question_data = _pending_questions.get(question_id)

    if not question_data:
        logger.warning(f"submit_user_answer: Question {question_id} not found")
        return False

    question_data["status"] = "answered"
    question_data["answer"] = answer
    question_data["answer_type"] = answer_type

    logger.info(f"submit_user_answer: Answer recorded for {question_id}: {answer}")
    return True
