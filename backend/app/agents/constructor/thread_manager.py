"""Thread management for LangGraph conversations with interrupt/resume support."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Store: session_id -> thread_id mapping
_session_threads: Dict[str, str] = {}

# Store: thread_id -> interrupt state
_thread_interrupts: Dict[str, Dict[str, Any]] = {}


def get_or_create_thread(session_id: str) -> str:
    """Get or create a thread_id for a session."""
    if session_id not in _session_threads:
        # Create new thread for this session
        thread_id = f"thread_{session_id}"
        _session_threads[session_id] = thread_id
        logger.info(f"Created new thread {thread_id} for session {session_id}")
    return _session_threads[session_id]


def store_interrupt(thread_id: str, interrupt_data: Dict[str, Any]) -> None:
    """Store interrupt state for a thread."""
    _thread_interrupts[thread_id] = interrupt_data
    logger.info(f"Stored interrupt for thread {thread_id}: {interrupt_data}")


def get_interrupt(thread_id: str) -> Optional[Dict[str, Any]]:
    """Get interrupt state for a thread."""
    return _thread_interrupts.get(thread_id)


def clear_interrupt(thread_id: str) -> None:
    """Clear interrupt state after resume."""
    if thread_id in _thread_interrupts:
        del _thread_interrupts[thread_id]
        logger.info(f"Cleared interrupt for thread {thread_id}")


def clear_session(session_id: str) -> None:
    """Clear all state for a session."""
    thread_id = _session_threads.pop(session_id, None)
    if thread_id:
        clear_interrupt(thread_id)
        logger.info(f"Cleared session {session_id} and thread {thread_id}")
