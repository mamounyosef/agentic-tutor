"""Node functions for the Constructor Coordinator Agent.

Each node represents a step in the course construction workflow.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END

from app.agents.base.llm import get_llm
from app.agents.base.utils import langchain_to_messages, messages_to_langchain
from app.agents.constructor.state import ConstructorState, create_initial_constructor_state
from .prompts import (
    COORDINATOR_SYSTEM_PROMPT,
    NEXT_ACTION_PROMPT,
    WELCOME_MESSAGE,
    PROGRESS_MESSAGES,
)

logger = logging.getLogger(__name__)


# Valid coordinator actions returned by the action router.
VALID_ACTIONS = {
    "collect_info",
    "request_files",
    "process_files",
    "analyze_structure",
    "generate_quizzes",
    "validate_course",
    "finalize",
    "respond",
}


# =============================================================================
# Node Functions
# =============================================================================

async def welcome_node(state: ConstructorState) -> Dict[str, Any]:
    """
    Welcome the creator and initialize the session.

    This is the entry point for new construction sessions.
    """
    if state.get("messages") and state.get("phase") != "welcome":
        # Entry-point node runs on each invoke; initialize only once.
        return {
            **state,
            "updated_at": datetime.utcnow().isoformat(),
        }

    # Generate welcome message
    welcome = WELCOME_MESSAGE

    return {
        "messages": [{
            "role": "assistant",
            "content": welcome,
            "timestamp": datetime.utcnow().isoformat(),
        }],
        "phase": "info_gathering",
        "current_agent": "coordinator",
        "progress": 0.05,
        "updated_at": datetime.utcnow().isoformat(),
    }


async def intake_node(state: ConstructorState) -> Dict[str, Any]:
    """
    Process incoming user messages and extract information.

    This node handles:
    - Course info extraction
    - Intent classification
    - Response generation
    """
    llm = get_llm(temperature=0.7)

    # Build context
    course_title = state.get("course_info", {}).get("title", "Not set")
    files_count = len(state.get("uploaded_files", []))
    topics_count = len(state.get("topics", []))
    questions_count = len(state.get("quiz_questions", []))

    # Format system prompt with current state
    system_prompt = COORDINATOR_SYSTEM_PROMPT.format(
        phase=state.get("phase", "welcome"),
        progress=state.get("progress", 0),
        course_title=course_title,
        files_count=files_count,
        topics_count=topics_count,
        questions_count=questions_count,
    )

    # Convert messages to LangChain format
    lc_messages = [SystemMessage(content=system_prompt)]
    lc_messages.extend(messages_to_langchain(state.get("messages", [])))

    # Get LLM response
    response = await llm.ainvoke(lc_messages)
    assistant_text = (getattr(response, "content", "") or "").strip()
    if not assistant_text:
        assistant_text = _default_coordinator_reply(state)

    # Extract course info from conversation if in info_gathering phase
    course_info_updates = {}
    if state.get("phase") == "info_gathering":
        course_info_updates = await _extract_course_info(state, assistant_text)

    return {
        "messages": [{
            "role": "assistant",
            "content": assistant_text,
            "timestamp": datetime.utcnow().isoformat(),
        }],
        "course_info": {**state.get("course_info", {}), **course_info_updates},
        "updated_at": datetime.utcnow().isoformat(),
    }


async def route_action_node(state: ConstructorState) -> Dict[str, Any]:
    """
    Determine the next action based on current state.

    This node analyzes the course construction state and decides
    what should happen next.
    """
    llm = get_llm(temperature=0.3)
    default_action = _determine_default_action(state)

    # For pipeline progression, prefer deterministic routing over model output.
    if default_action in {
        "process_files",
        "analyze_structure",
        "generate_quizzes",
        "validate_course",
        "finalize",
    }:
        return {
            "pending_subagent": default_action,
            "updated_at": datetime.utcnow().isoformat(),
        }

    # Determine what action to take
    has_course_info = bool(
        state.get("course_info", {}).get("title") and
        state.get("course_info", {}).get("description")
    )
    files_count = len(state.get("uploaded_files", []))
    processed_count = len(state.get("processed_files", []))
    topics_count = len(state.get("topics", []))
    questions_count = len(state.get("quiz_questions", []))
    validation_passed = state.get("validation_passed", False)

    action_prompt = NEXT_ACTION_PROMPT.format(
        phase=state.get("phase", "welcome"),
        has_course_info=has_course_info,
        files_count=files_count,
        processed_count=processed_count,
        topics_count=topics_count,
        questions_count=questions_count,
        validation_passed=validation_passed,
    )

    response = await llm.ainvoke(action_prompt)

    # Parse action from response
    try:
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        action_data = json.loads(content.strip())
        next_action = str(action_data.get("action", "respond")).strip().lower()
        if next_action not in VALID_ACTIONS:
            next_action = default_action
    except (json.JSONDecodeError, KeyError):
        # Default based on state
        next_action = default_action

    return {
        "pending_subagent": next_action,
        "updated_at": datetime.utcnow().isoformat(),
    }


async def dispatch_node(state: ConstructorState) -> Dict[str, Any]:
    """
    Dispatch to the appropriate sub-agent based on pending action.

    This node prepares state for sub-agent invocation.
    """
    action = state.get("pending_subagent", "respond")

    # Map actions to agents
    agent_mapping = {
        "process_files": "ingestion",
        "analyze_structure": "structure",
        "generate_quizzes": "quiz",
        "validate_course": "validation",
    }

    target_agent = agent_mapping.get(action, "coordinator")

    return {
        "current_agent": target_agent,
        "updated_at": datetime.utcnow().isoformat(),
    }


async def respond_node(state: ConstructorState) -> Dict[str, Any]:
    """
    Generate a response to the user based on current state.

    This is the default node for conversational responses.
    """
    llm = get_llm(temperature=0.7)

    # Build context for response
    system_prompt = COORDINATOR_SYSTEM_PROMPT.format(
        phase=state.get("phase", "welcome"),
        progress=state.get("progress", 0),
        course_title=state.get("course_info", {}).get("title", "Not set"),
        files_count=len(state.get("uploaded_files", [])),
        topics_count=len(state.get("topics", [])),
        questions_count=len(state.get("quiz_questions", [])),
    )

    lc_messages = [SystemMessage(content=system_prompt)]
    lc_messages.extend(messages_to_langchain(state.get("messages", [])))

    response = await llm.ainvoke(lc_messages)
    assistant_text = (getattr(response, "content", "") or "").strip()
    if not assistant_text:
        assistant_text = _default_coordinator_reply(state)

    return {
        "messages": [{
            "role": "assistant",
            "content": assistant_text,
            "timestamp": datetime.utcnow().isoformat(),
        }],
        "pending_subagent": None,
        "updated_at": datetime.utcnow().isoformat(),
    }


async def finalize_node(state: ConstructorState) -> Dict[str, Any]:
    """
    Finalize the course and prepare for publishing.

    This node marks the course as complete and ready for students.
    """
    course_title = state.get("course_info", {}).get("title", "Your Course")

    message = PROGRESS_MESSAGES["course_published"].format(title=course_title)

    return {
        "messages": [{
            "role": "assistant",
            "content": message,
            "timestamp": datetime.utcnow().isoformat(),
        }],
        "phase": "complete",
        "progress": 1.0,
        "current_agent": "coordinator",
        "updated_at": datetime.utcnow().isoformat(),
    }


# =============================================================================
# Helper Functions
# =============================================================================

async def _extract_course_info(
    state: ConstructorState,
    assistant_response: str
) -> Dict[str, Any]:
    """Extract course information from conversation."""
    llm = get_llm(temperature=0.3)

    recent_messages = state["messages"][-4:] if len(state["messages"]) >= 4 else state["messages"]
    serializable_messages = []
    for msg in recent_messages:
        if isinstance(msg, dict):
            serializable_messages.append(msg)
        else:
            serializable_messages.extend(langchain_to_messages([msg]))

    extraction_prompt = f"""Analyze the conversation and extract course information.

Current known info: {json.dumps(state.get('course_info', {}))}

Recent messages:
{json.dumps(serializable_messages)}

Extract any mentioned:
- title: Course title
- description: Course description
- difficulty: Difficulty level (beginner/intermediate/advanced)
- tags: List of relevant tags/topics

Return JSON with only the fields that can be extracted or updated:
{{"title": "...", "description": "...", "difficulty": "...", "tags": [...]}}
"""

    try:
        response = await llm.ainvoke(extraction_prompt)
        content = response.content

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]

        return json.loads(content.strip())
    except Exception:
        return {}


def _determine_default_action(state: ConstructorState) -> str:
    """Determine default action based on state."""
    phase = state.get("phase", "welcome")
    course_info = state.get("course_info", {})
    uploaded_files = state.get("uploaded_files", [])
    processed_files = state.get("processed_files", [])
    topics = state.get("topics", [])
    questions = state.get("quiz_questions", [])

    if phase in ["welcome", "info_gathering"]:
        if not course_info.get("title") or not course_info.get("description"):
            return "collect_info"
        return "request_files"

    if uploaded_files and len(processed_files) < len(uploaded_files):
        return "process_files"

    if processed_files and not topics:
        return "analyze_structure"

    if topics and not questions:
        return "generate_quizzes"

    if questions and not state.get("validation_passed"):
        return "validate_course"

    if state.get("validation_passed"):
        return "finalize"

    return "respond"


def _default_coordinator_reply(state: ConstructorState) -> str:
    """Fallback assistant reply when the model returns empty content."""
    course_info = state.get("course_info", {})
    if not course_info.get("title") or not course_info.get("description"):
        return (
            "Let's start with your course basics. Please share:\n"
            "1) Course title\n"
            "2) Short description\n"
            "3) Difficulty (beginner/intermediate/advanced)"
        )
    if not state.get("uploaded_files"):
        return (
            "Great, I have the course basics. Next, upload your materials "
            "(PDF, PPT/PPTX, DOCX, TXT, or video) so I can process them."
        )
    return "Got it. Tell me what you want to do next, and I'll guide you step by step."


# =============================================================================
# Routing Functions
# =============================================================================

def route_by_phase(state: ConstructorState) -> str:
    """Route to appropriate node based on phase and state."""
    action = state.get("pending_subagent", "respond")

    action_to_node = {
        # Intake already generated assistant guidance for this turn.
        # End the turn instead of recursively looping without new user input.
        "collect_info": "end_turn",
        "request_files": "end_turn",
        "process_files": "dispatch",
        "analyze_structure": "dispatch",
        "generate_quizzes": "dispatch",
        "validate_course": "dispatch",
        "finalize": "finalize",
        "respond": "end_turn",
    }

    return action_to_node.get(action, "end_turn")


def should_continue(state: ConstructorState) -> str:
    """Determine if the workflow should continue or end."""
    if state.get("phase") == "complete":
        return "end"
    return "continue"


def route_subagent(state: ConstructorState) -> str:
    """Route to the appropriate sub-agent."""
    return state.get("current_agent", "coordinator")
