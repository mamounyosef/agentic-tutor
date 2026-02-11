"""Utilities for handling mixed dict/LangChain message shapes."""

from datetime import datetime
from typing import Any, Iterable, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


def message_content(message: Any) -> str:
    """Extract plain-text content from dict or LangChain message objects."""
    if isinstance(message, dict):
        content = message.get("content", "")
        return content if isinstance(content, str) else str(content)

    if isinstance(message, BaseMessage):
        content = getattr(message, "content", "")
        return content if isinstance(content, str) else str(content)

    return str(message) if message is not None else ""


def message_role(message: Any) -> str:
    """Infer a normalized role for dict/LangChain message objects."""
    if isinstance(message, dict):
        role = str(message.get("role", "user")).lower()
        return role

    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, SystemMessage):
        return "system"

    return "user"


def is_assistant_message(message: Any) -> bool:
    """Return True when the message is an assistant/AI message."""
    return message_role(message) == "assistant"


def make_user_message(content: str) -> dict[str, str]:
    """Create canonical user message dict."""
    return {
        "role": "user",
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
    }


def make_assistant_message(content: str) -> dict[str, str]:
    """Create canonical assistant message dict."""
    return {
        "role": "assistant",
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
    }


def latest_assistant_content(messages: Iterable[Any]) -> Optional[str]:
    """Return the newest assistant message content, if any."""
    for message in reversed(list(messages)):
        if is_assistant_message(message):
            content = message_content(message).strip()
            if content:
                return content
    return None


def append_user_message(messages: List[Any], content: str) -> List[Any]:
    """Return a new list with one canonical user message appended."""
    return [*messages, make_user_message(content)]
