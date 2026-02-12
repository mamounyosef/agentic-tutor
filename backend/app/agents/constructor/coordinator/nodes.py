"""Node functions for the Constructor Coordinator Agent.

Each node represents a step in the course construction workflow.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END

from app.agents.base.llm import get_llm
from app.agents.base.message_utils import is_assistant_message, message_content, message_role
from app.agents.base.utils import langchain_to_messages, messages_to_langchain
from app.agents.constructor.state import (
    ConstructorState,
    create_initial_constructor_state,
    resolve_creator_id,
)
from app.agents.constructor.tools.storage import create_course_record, update_course_record
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
    if state.get("messages"):
        # Entry-point node runs on each invoke. Never return full state here
        # because messages are reducer-managed and full echoing can duplicate
        # chat history on every turn.
        return {
            "phase": "info_gathering" if state.get("phase") == "welcome" else state.get("phase"),
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
    llm = get_llm(temperature=0.3)

    deterministic_reply = _deterministic_coordinator_reply(state)
    if deterministic_reply:
        assistant_text = deterministic_reply
    else:
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
        elif _has_course_basics(state) and _looks_like_basics_request(assistant_text):
            assistant_text = _default_coordinator_reply(state)

    # Extract course info from conversation if in info_gathering phase.
    # Use deterministic parsing first, then enrich via LLM extraction.
    course_info_updates: Dict[str, Any] = _extract_course_info_heuristic(state)
    if state.get("phase") == "info_gathering":
        llm_updates = await _extract_course_info(state, assistant_text)
        course_info_updates = _merge_course_info_updates(course_info_updates, llm_updates)
    merged_course_info = {**state.get("course_info", {}), **course_info_updates}

    # Ensure a concrete course record exists once we have required basics.
    # This keeps downstream ingestion/structure/quiz steps aligned to a real DB course_id.
    course_id = state.get("course_id")
    has_min_course_info = bool(
        merged_course_info.get("title") and merged_course_info.get("description")
    )
    creator_id = resolve_creator_id(state.get("creator_id"), state.get("session_id", ""))

    if has_min_course_info and not course_id and creator_id is not None:
        try:
            create_result = await create_course_record.ainvoke(
                {
                    "creator_id": creator_id,
                    "title": merged_course_info.get("title"),
                    "description": merged_course_info.get("description"),
                    "difficulty": merged_course_info.get("difficulty", "beginner"),
                }
            )
            if create_result.get("success") and create_result.get("course_id"):
                course_id = int(create_result["course_id"])
        except Exception as exc:
            logger.warning("Failed to create course record: %s", exc)

    # If course basics were updated after creation, keep DB record in sync.
    if course_id and course_info_updates:
        try:
            await update_course_record.ainvoke(
                {
                    "course_id": int(course_id),
                    "title": merged_course_info.get("title"),
                    "description": merged_course_info.get("description"),
                    "difficulty": merged_course_info.get("difficulty", "beginner"),
                }
            )
        except Exception as exc:
            logger.warning("Failed to update course record %s: %s", course_id, exc)

    return {
        "messages": [{
            "role": "assistant",
            "content": assistant_text,
            "timestamp": datetime.utcnow().isoformat(),
        }],
        "course_info": merged_course_info,
        "course_id": course_id,
        **({"creator_id": creator_id} if creator_id is not None else {}),
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
    # If a sub-agent already produced an assistant message this turn,
    # don't generate an extra coordinator reply.
    pipeline_actions = {
        "process_files",
        "analyze_structure",
        "generate_quizzes",
        "validate_course",
    }
    pending_action = state.get("pending_subagent")
    messages = state.get("messages", [])
    if (
        pending_action in pipeline_actions
        and messages
        and is_assistant_message(messages[-1])
    ):
        return {
            "pending_subagent": None,
            "updated_at": datetime.utcnow().isoformat(),
        }

    llm = get_llm(temperature=0.3)

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
    elif _has_course_basics(state) and _looks_like_basics_request(assistant_text):
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
    course_info = state.get("course_info", {})
    course_title = course_info.get("title", "Your Course")
    course_id = state.get("course_id")
    creator_id = resolve_creator_id(state.get("creator_id"), state.get("session_id", ""))

    # Ensure there's a persisted course and mark it published.
    try:
        if (
            not course_id
            and creator_id is not None
            and course_info.get("title")
            and course_info.get("description")
        ):
            created = await create_course_record.ainvoke(
                {
                    "creator_id": creator_id,
                    "title": course_info.get("title"),
                    "description": course_info.get("description"),
                    "difficulty": course_info.get("difficulty", "beginner"),
                }
            )
            if created.get("success") and created.get("course_id"):
                course_id = int(created["course_id"])

        if course_id:
            await update_course_record.ainvoke(
                {
                    "course_id": int(course_id),
                    "is_published": True,
                }
            )
    except Exception as exc:
        logger.warning("Failed to finalize/publish course record: %s", exc)

    message = PROGRESS_MESSAGES["course_published"].format(title=course_title)

    return {
        "messages": [{
            "role": "assistant",
            "content": message,
            "timestamp": datetime.utcnow().isoformat(),
        }],
        "course_id": course_id,
        **({"creator_id": creator_id} if creator_id is not None else {}),
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
        parsed = _extract_json_object(content.strip())
        if not isinstance(parsed, dict):
            return {}
        return _normalize_course_info(parsed)
    except Exception:
        return {}


def _extract_json_object(text: str) -> Any:
    """Extract a JSON object from raw model output."""
    if not text:
        return {}

    # Fast path: whole payload is JSON.
    try:
        return json.loads(text)
    except Exception:
        pass

    # Fallback: first {...} block in the response.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return {}
    return {}


def _normalize_difficulty(value: str) -> str:
    """Normalize difficulty values to supported canonical values."""
    lowered = (value or "").strip().lower()
    if not lowered:
        return ""
    if "beginner" in lowered:
        return "beginner"
    if "intermediate" in lowered:
        return "intermediate"
    if "advanced" in lowered:
        return "advanced"
    # Keep unknown values out to avoid polluting state with free-form labels.
    return ""


def _normalize_course_info(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and sanitize extracted course info fields."""
    updates: Dict[str, Any] = {}

    title = str(raw.get("title", "")).strip()
    # Keep title bounded to title-only text even when a model returns merged
    # "Title + Description + Difficulty" blocks.
    title = re.split(
        r"(?is)(?:\n|(?:\s{2,}))(?:description|goal|objective|difficulty(?:\s*level)?)\s*:",
        title,
        maxsplit=1,
    )[0].strip()
    title = " ".join(title.split())
    description = str(raw.get("description", "")).strip()
    difficulty = _normalize_difficulty(str(raw.get("difficulty", "")))
    tags = raw.get("tags")

    if title:
        updates["title"] = title[:255]
    if description:
        updates["description"] = description
    if difficulty:
        updates["difficulty"] = difficulty
    if isinstance(tags, list):
        normalized_tags = [str(t).strip() for t in tags if str(t).strip()]
        if normalized_tags:
            updates["tags"] = normalized_tags

    return updates


def _merge_course_info_updates(
    base_updates: Dict[str, Any],
    llm_updates: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge extraction updates with deterministic values taking precedence."""
    merged = dict(base_updates or {})
    for key, value in (llm_updates or {}).items():
        if key not in merged or not merged.get(key):
            merged[key] = value
    return merged


def _extract_course_info_heuristic(state: ConstructorState) -> Dict[str, Any]:
    """Deterministically extract course info from recent user messages."""
    messages = state.get("messages", [])
    user_texts = [
        message_content(m)
        for m in messages[-8:]
        if message_role(m) == "user"
    ]
    if not user_texts:
        return {}

    combined = "\n".join(t for t in user_texts if t).strip()
    if not combined:
        return {}

    updates: Dict[str, Any] = {}

    title_match = re.search(
        r"(?is)(?:^|\n)\s*(?:course\s*title|title)(?:\s*\([^)]*\))?\s*:\s*(.+?)"
        r"(?=(?:\s+(?:difficulty(?:\s*level)?|description|goal|objective)\s*:)|\n|$)",
        combined,
    )
    if title_match:
        updates["title"] = title_match.group(1).strip()

    desc_match = re.search(
        r"(?is)(?:^|\n)\s*(?:description|goal|objective)(?:\s*\([^)]*\))?\s*:\s*(.+?)"
        r"(?=(?:\n\s*(?:course\s*title|title|difficulty(?:\s*level)?|description|goal|objective)"
        r"(?:\s*\([^)]*\))?\s*:)|\Z)",
        combined,
    )
    if desc_match:
        updates["description"] = desc_match.group(1).strip()

    diff_match = re.search(
        r"(?im)^\s*(?:difficulty(?:\s*level)?)(?:\s*\([^)]*\))?\s*:\s*(.+)$",
        combined,
    )
    if diff_match:
        normalized = _normalize_difficulty(diff_match.group(1))
        if normalized:
            updates["difficulty"] = normalized

    # Secondary fallback: if title/description are still missing, try compact patterns.
    if "title" not in updates:
        m = re.search(r"(?i)\bmy course(?: title)? is\s+(.+?)(?:[.\n]|$)", combined)
        if m:
            updates["title"] = m.group(1).strip()
    if "description" not in updates:
        m = re.search(r"(?i)\b(?:students will|learners will|goal is to)\s+(.+?)(?:[.\n]|$)", combined)
        if m:
            updates["description"] = m.group(1).strip()

    return _normalize_course_info(updates)


def _determine_default_action(state: ConstructorState) -> str:
    """Determine default action based on state."""
    phase = state.get("phase", "welcome")
    course_info = state.get("course_info", {})
    uploaded_files = state.get("uploaded_files", [])
    processed_files = state.get("processed_files", [])
    topics = state.get("topics", [])
    questions = state.get("quiz_questions", [])
    structure_result = state.get("subagent_results", {}).get("structure", {})
    structure_completed = bool(structure_result.get("status"))

    # Prioritize concrete workflow progression whenever files/results exist,
    # even if phase is still marked as info_gathering.
    if uploaded_files and len(processed_files) < len(uploaded_files):
        return "process_files"

    if processed_files and not topics:
        # Avoid infinite analyze -> no-topics -> analyze loops when structure
        # already completed but couldn't derive topics from current materials.
        # Allow an explicit user-triggered retry (e.g., "create the course now").
        if structure_completed and not _should_retry_structure(state):
            return "respond"
        return "analyze_structure"

    if topics and not questions:
        return "generate_quizzes"

    if questions and not state.get("validation_passed"):
        return "validate_course"

    if state.get("validation_passed"):
        return "finalize"

    if phase in ["welcome", "info_gathering"]:
        if not course_info.get("title") or not course_info.get("description"):
            return "collect_info"
        return "request_files"

    return "respond"


def _default_coordinator_reply(state: ConstructorState) -> str:
    """Fallback assistant reply when the model returns empty content."""
    course_info = state.get("course_info", {})
    uploaded_files = state.get("uploaded_files", [])
    processed_files = state.get("processed_files", [])
    topics = state.get("topics", [])
    questions = state.get("quiz_questions", [])
    structure_result = state.get("subagent_results", {}).get("structure", {})
    structure_completed = bool(structure_result.get("status"))

    if not course_info.get("title") or not course_info.get("description"):
        return (
            "Let's start with your course basics. Please share:\n"
            "1) Course title\n"
            "2) Short description\n"
            "3) Difficulty (beginner/intermediate/advanced)"
        )
    if not uploaded_files:
        return (
            "Great, I have the course basics. Next, upload your materials "
            "(PDF, PPT/PPTX, DOCX, TXT, or video) so I can process them."
        )
    if len(processed_files) < len(uploaded_files):
        return (
            "I can see uploaded material is pending processing. "
            "Say 'create the course now' and I'll start ingestion."
        )
    if processed_files and not topics:
        if structure_completed:
            return (
                "I processed your files, but I couldn't derive a reliable course structure "
                "from the current content. Please upload clearer supporting material "
                "(slides/PDF/notes) or provide a short outline, and I'll continue."
            )
        return "Your files are processed. Next step is structure analysis."
    if topics and not questions:
        return "Course structure is ready. Next step is quiz generation."
    if questions and not state.get("validation_passed"):
        return "Quiz bank is ready. Next step is validation before publishing."
    if state.get("validation_passed"):
        return "Validation passed. Finalizing and publishing your course."
    return "Tell me what you want to do next and I'll continue the workflow."


def _deterministic_coordinator_reply(state: ConstructorState) -> str:
    """Return a deterministic coordinator reply for common control intents."""
    messages = state.get("messages", [])
    user_messages = [message_content(m).strip() for m in messages if message_role(m) == "user"]
    if not user_messages:
        return ""

    last_user = user_messages[-1].lower()
    uploaded_files = state.get("uploaded_files", [])
    processed_files = state.get("processed_files", [])
    has_basics = _has_course_basics(state)

    if not has_basics:
        return ""

    asks_upload_visibility = (
        ("upload" in last_user or "uploaded" in last_user)
        and ("can you see" in last_user or "do you see" in last_user or "did you get" in last_user)
    )
    asks_to_create = (
        "create the course" in last_user
        or "build the course" in last_user
        or "create it" in last_user
    )
    asks_status = (
        "are you done" in last_user
        or "done?" in last_user
        or "status" in last_user
        or "progress" in last_user
    )

    if asks_upload_visibility:
        if not uploaded_files:
            return "I do not see uploaded files in this session yet. Please upload a file and I will process it."
        names = [str(f.get("original_filename") or f.get("file_path") or "file") for f in uploaded_files]
        preview = ", ".join(names[:3])
        if len(names) > 3:
            preview += f", and {len(names) - 3} more"
        return f"Yes, I can see {len(names)} uploaded file(s): {preview}. If you want, say 'create the course now' and I will continue processing."

    if asks_to_create and uploaded_files:
        if len(processed_files) < len(uploaded_files):
            return "Great. I have your course basics and uploaded materials. I will continue with ingestion and then build structure, quizzes, and validation."
        return "Great. Your files are already processed, so I will proceed with structure analysis, quiz generation, and validation."

    if asks_status:
        if uploaded_files and len(processed_files) < len(uploaded_files):
            return "I am still processing uploaded materials. Once processing finishes, I will continue with structure analysis and quiz generation."

        next_action = _determine_default_action(state)
        action_to_status = {
            "collect_info": "waiting for course basics",
            "request_files": "waiting for course materials upload",
            "process_files": "ingesting uploaded files",
            "analyze_structure": "analyzing course structure",
            "generate_quizzes": "generating quiz bank",
            "validate_course": "running course validation",
            "finalize": "finalizing course publication",
            "respond": "waiting for your next instruction",
        }
        return (
            f"Current status: {action_to_status.get(next_action, 'in progress')}. "
            f"Progress is {int(float(state.get('progress', 0.0)) * 100)}%."
        )

    return ""


def _has_course_basics(state: ConstructorState) -> bool:
    """Return True when required course basics are already present in state."""
    info = state.get("course_info", {})
    return bool(info.get("title") and info.get("description"))


def _looks_like_basics_request(text: str) -> bool:
    """Heuristic: detect responses that re-ask for title/description/difficulty."""
    lowered = (text or "").lower()
    return (
        ("title" in lowered or "course title" in lowered)
        and ("description" in lowered or "summary" in lowered or "goal" in lowered)
        and ("difficulty" in lowered or "beginner" in lowered or "intermediate" in lowered or "advanced" in lowered)
    )


def _should_retry_structure(state: ConstructorState) -> bool:
    """Check whether the latest user message explicitly asks to continue/build."""
    messages = state.get("messages", [])
    user_messages = [message_content(m).strip().lower() for m in messages if message_role(m) == "user"]
    if not user_messages:
        return False
    last_user = user_messages[-1]
    retry_phrases = (
        "create the course",
        "build the course",
        "proceed",
        "continue",
        "go ahead",
        "analyze",
        "retry",
    )
    return any(phrase in last_user for phrase in retry_phrases)


# =============================================================================
# Routing Functions
# =============================================================================

def route_by_phase(state: ConstructorState) -> str:
    """Route to appropriate node based on phase and state."""
    action = state.get("pending_subagent", "respond")

    # Check if we just sent a response and should wait for user input
    # If the last message was from assistant (not user), end the turn
    messages = state.get("messages", [])
    just_responded = (
        len(messages) > 0 and
        is_assistant_message(messages[-1])
    )

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
        "respond": "end_turn" if just_responded else "respond",
    }

    # Special case: if we're in info_gathering with no course info yet,
    # and we just responded, end turn to wait for user input
    if (
        state.get("phase") == "info_gathering" and
        not state.get("course_info", {}).get("title") and
        just_responded
    ):
        return "end_turn"

    return action_to_node.get(action, "end_turn")


def should_continue(state: ConstructorState) -> str:
    """Determine if the workflow should continue or end."""
    # End if phase is complete
    if state.get("phase") == "complete":
        return "end"

    # Check if there's a new user message (last message is from user)
    messages = state.get("messages", [])
    if len(messages) == 0:
        return "continue"

    last_message = messages[-1]
    # If the last message was from the user, continue processing
    # If it was from the assistant, we've already responded - end to wait for new input
    if message_role(last_message) == "user":
        return "continue"

    # Last message was from assistant - we've completed our response, end turn
    return "end"


def route_subagent(state: ConstructorState) -> str:
    """Route to the appropriate sub-agent."""
    return state.get("current_agent", "coordinator")
