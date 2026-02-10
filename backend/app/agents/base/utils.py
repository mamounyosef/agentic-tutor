"""Shared utilities for agent implementations."""

import functools
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from .state import Message

logger = logging.getLogger(__name__)

T = TypeVar("T")


def format_messages_for_display(messages: List[Dict[str, Any]]) -> List[Message]:
    """
    Format internal message dicts as Message objects for display.

    Args:
        messages: List of message dictionaries

    Returns:
        List of Message objects
    """
    result = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", datetime.utcnow().isoformat())
        result.append(Message(role=role, content=content, timestamp=timestamp))
    return result


def messages_to_langchain(
    messages: List[Any]
) -> List[BaseMessage]:
    """
    Convert message dicts to LangChain message objects.

    Args:
        messages: List of message dictionaries with 'role' and 'content'

    Returns:
        List of LangChain message objects
    """
    result = []
    for msg in messages:
        # Pass through LangChain message objects unchanged.
        if isinstance(msg, BaseMessage):
            result.append(msg)
            continue

        # Backward-compatible support for dict-style messages.
        if isinstance(msg, dict):
            role = str(msg.get("role", "")).lower()
            content = msg.get("content", "")

            if role == "user":
                result.append(HumanMessage(content=content))
            elif role == "assistant":
                result.append(AIMessage(content=content))
            elif role == "system":
                result.append(SystemMessage(content=content))
            else:
                # Default to human message
                result.append(HumanMessage(content=content))
            continue

        # Fallback: stringify unknown message shapes as user content.
        result.append(HumanMessage(content=str(msg)))

    return result


def langchain_to_messages(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    """
    Convert LangChain message objects to message dicts.

    Args:
        messages: List of LangChain message objects

    Returns:
        List of message dictionaries
    """
    result = []
    for msg in messages:
        role = "user"
        if isinstance(msg, AIMessage):
            role = "assistant"
        elif isinstance(msg, SystemMessage):
            role = "system"

        result.append({
            "role": role,
            "content": msg.content,
            "timestamp": datetime.utcnow().isoformat(),
        })

    return result


def log_agent_action(agent_name: str):
    """
    Decorator to log agent node actions.

    Args:
        agent_name: Name of the agent for logging

    Usage:
        @log_agent_action("coordinator")
        async def my_node(state):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger.info(f"[{agent_name}] Starting {func.__name__}")
            try:
                result = await func(*args, **kwargs)
                logger.info(f"[{agent_name}] Completed {func.__name__}")
                return result
            except Exception as e:
                logger.error(f"[{agent_name}] Error in {func.__name__}: {e}")
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger.info(f"[{agent_name}] Starting {func.__name__}")
            try:
                result = func(*args, **kwargs)
                logger.info(f"[{agent_name}] Completed {func.__name__}")
                return result
            except Exception as e:
                logger.error(f"[{agent_name}] Error in {func.__name__}: {e}")
                raise

        if asyncio is not None and functools.coroutines.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Import asyncio conditionally for the decorator
import asyncio
import functools


def calculate_progress(
    completed_steps: int,
    total_steps: int,
    base_progress: float = 0.0,
    max_progress: float = 1.0,
) -> float:
    """
    Calculate progress percentage within a range.

    Args:
        completed_steps: Number of completed steps
        total_steps: Total number of steps
        base_progress: Minimum progress (default 0.0)
        max_progress: Maximum progress (default 1.0)

    Returns:
        Progress as a float between base_progress and max_progress
    """
    if total_steps == 0:
        return base_progress

    step_progress = completed_steps / total_steps
    return base_progress + (step_progress * (max_progress - base_progress))


def truncate_text(text: str, max_length: int = 1000, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length.

    Args:
        text: Text to truncate
        max_length: Maximum length (default 1000)
        suffix: Suffix to add when truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
