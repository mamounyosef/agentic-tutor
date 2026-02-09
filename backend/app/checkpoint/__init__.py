"""LangGraph checkpointers for conversation memory management.

This module provides persistent conversation state storage for both Constructor
and Tutor workflows using LangGraph's checkpointing system.

Checkpointers enable:
- Resumable sessions after interruptions
- Conversation history tracking
- State persistence across agent invocations
"""

import os
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from ..core.config import Settings, get_settings


# ==============================================================================
# CONSTRUCTOR CHECKPOINTER
# ==============================================================================

def get_constructor_checkpointer(session_id: str) -> SqliteSaver:
    """
    Get or create a LangGraph checkpointer for a Constructor session.

    The Constructor checkpointer stores:
    - Conversation history with the course creator
    - Course construction state (files uploaded, topics created, etc.)
    - Agent coordination state
    - Progress tracking

    Args:
        session_id: Unique identifier for the construction session

    Returns:
        SqliteSaver instance for storing session state

    Example:
        checkpointer = get_constructor_checkpointer("session_abc123")
        # Use in LangGraph compiled graph
    """
    settings = get_settings()

    # Ensure checkpoint directory exists
    checkpoint_dir = Path(settings.CONSTRUCTOR_CHECKPOINT_PATH)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # Each session gets its own SQLite file
    checkpoint_path = checkpoint_dir / f"session_{session_id}.db"

    return SqliteSaver.from_conn_string(str(checkpoint_path))


# ==============================================================================
# TUTOR CHECKPOINTER
# ==============================================================================

def get_tutor_checkpointer(session_id: str) -> SqliteSaver:
    """
    Get or create a LangGraph checkpointer for a Tutor session.

    The Tutor checkpointer stores:
    - Conversation history with the student
    - Current topic and mastery snapshot
    - Session state (what actions have been taken)
    - Learning progress tracking

    Args:
        session_id: Unique identifier for the tutoring session

    Returns:
        SqliteSaver instance for storing session state

    Example:
        checkpointer = get_tutor_checkpointer("session_xyz789")
        # Use in LangGraph compiled graph
    """
    settings = get_settings()

    # Ensure checkpoint directory exists
    checkpoint_dir = Path(settings.TUTOR_CHECKPOINT_PATH)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # Each session gets its own SQLite file
    checkpoint_path = checkpoint_dir / f"session_{session_id}.db"

    return SqliteSaver.from_conn_string(str(checkpoint_path))


# ==============================================================================
# CHECKPOINT MANAGEMENT UTILITIES
# ==============================================================================

def list_constructor_sessions() -> list[str]:
    """
    List all existing Constructor session IDs.

    Returns:
        List of session IDs that have checkpoint files

    Example:
        sessions = list_constructor_sessions()
        # Returns: ["session_abc123", "session_def456", ...]
    """
    settings = get_settings()
    checkpoint_dir = Path(settings.CONSTRUCTOR_CHECKPOINT_PATH)

    if not checkpoint_dir.exists():
        return []

    # Extract session IDs from .db files
    session_files = list(checkpoint_dir.glob("session_*.db"))
    return [
        f.stem.replace("session_", "")
        for f in session_files
    ]


def list_tutor_sessions() -> list[str]:
    """
    List all existing Tutor session IDs.

    Returns:
        List of session IDs that have checkpoint files

    Example:
        sessions = list_tutor_sessions()
        # Returns: ["session_xyz789", "session_123", ...]
    """
    settings = get_settings()
    checkpoint_dir = Path(settings.TUTOR_CHECKPOINT_PATH)

    if not checkpoint_dir.exists():
        return []

    # Extract session IDs from .db files
    session_files = list(checkpoint_dir.glob("session_*.db"))
    return [
        f.stem.replace("session_", "")
        for f in session_files
    ]


def delete_constructor_checkpointer(session_id: str) -> bool:
    """
    Delete a Constructor session's checkpoint file.

    Useful for cleaning up old sessions.

    Args:
        session_id: The session ID to delete

    Returns:
        True if deleted, False if file didn't exist
    """
    settings = get_settings()
    checkpoint_dir = Path(settings.CONSTRUCTOR_CHECKPOINT_PATH)
    checkpoint_path = checkpoint_dir / f"session_{session_id}.db"

    if checkpoint_path.exists():
        checkpoint_path.unlink()
        return True
    return False


def delete_tutor_checkpointer(session_id: str) -> bool:
    """
    Delete a Tutor session's checkpoint file.

    Useful for cleaning up old sessions.

    Args:
        session_id: The session ID to delete

    Returns:
        True if deleted, False if file didn't exist
    """
    settings = get_settings()
    checkpoint_dir = Path(settings.TUTOR_CHECKPOINT_PATH)
    checkpoint_path = checkpoint_dir / f"session_{session_id}.db"

    if checkpoint_path.exists():
        checkpoint_path.unlink()
        return True
    return False


def get_constructor_checkpoint_path(session_id: str) -> str:
    """
    Get the file path for a Constructor session checkpoint.

    Args:
        session_id: The session ID

    Returns:
        Full file path as string
    """
    settings = get_settings()
    checkpoint_dir = Path(settings.CONSTRUCTOR_CHECKPOINT_PATH)
    return str(checkpoint_dir / f"session_{session_id}.db")


def get_tutor_checkpoint_path(session_id: str) -> str:
    """
    Get the file path for a Tutor session checkpoint.

    Args:
        session_id: The session ID

    Returns:
        Full file path as string
    """
    settings = get_settings()
    checkpoint_dir = Path(settings.TUTOR_CHECKPOINT_PATH)
    return str(checkpoint_dir / f"session_{session_id}.db")


# ==============================================================================
# CHECKPOINT STATE SERIALIZERS (Optional)
# ==============================================================================

class ConstructorSessionState:
    """
    Serializable state for Constructor sessions.

    This class defines what state gets persisted in the checkpointer.
    When a conversation resumes, this state is loaded to continue where it left off.

    Attributes:
        session_id: Unique session identifier
        creator_id: ID of the course creator
        course_id: ID of course being built (None until created)
        phase: Current construction phase
        messages: Conversation history
        uploaded_files: List of files uploaded
        course_structure: Course hierarchy being built
        subagent_results: Results from sub-agents
    """

    def __init__(
        self,
        session_id: str,
        creator_id: int,
        course_id: int | None = None,
        phase: str = "welcome",
        messages: list | None = None,
        uploaded_files: list | None = None,
        course_structure: dict | None = None,
        subagent_results: dict | None = None
    ):
        self.session_id = session_id
        self.creator_id = creator_id
        self.course_id = course_id
        self.phase = phase
        self.messages = messages or []
        self.uploaded_files = uploaded_files or []
        self.course_structure = course_structure or {}
        self.subagent_results = subagent_results or {}

    def to_dict(self) -> dict:
        """Convert state to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "creator_id": self.creator_id,
            "course_id": self.course_id,
            "phase": self.phase,
            "messages": self.messages,
            "uploaded_files": self.uploaded_files,
            "course_structure": self.course_structure,
            "subagent_results": self.subagent_results
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConstructorSessionState":
        """Create state from dictionary (for deserialization)."""
        return cls(
            session_id=data["session_id"],
            creator_id=data["creator_id"],
            course_id=data.get("course_id"),
            phase=data["phase"],
            messages=data.get("messages", []),
            uploaded_files=data.get("uploaded_files", []),
            course_structure=data.get("course_structure", {}),
            subagent_results=data.get("subagent_results", {})
        )


class TutorSessionState:
    """
    Serializable state for Tutor sessions.

    This class defines what state gets persisted in the checkpointer.

    Attributes:
        session_id: Unique session identifier
        student_id: ID of the student
        course_id: ID of course being studied
        messages: Conversation history
        current_topic: Topic currently being discussed
        mastery_snapshot: Dictionary of topic mastery scores
        session_goal: Learning goal for this session
        topics_covered: List of topics discussed in this session
    """

    def __init__(
        self,
        session_id: str,
        student_id: int,
        course_id: int,
        messages: list | None = None,
        current_topic: dict | None = None,
        mastery_snapshot: dict | None = None,
        session_goal: str | None = None,
        topics_covered: list | None = None
    ):
        self.session_id = session_id
        self.student_id = student_id
        self.course_id = course_id
        self.messages = messages or []
        self.current_topic = current_topic
        self.mastery_snapshot = mastery_snapshot or {}
        self.session_goal = session_goal
        self.topics_covered = topics_covered or []

    def to_dict(self) -> dict:
        """Convert state to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "student_id": self.student_id,
            "course_id": self.course_id,
            "messages": self.messages,
            "current_topic": self.current_topic,
            "mastery_snapshot": self.mastery_snapshot,
            "session_goal": self.session_goal,
            "topics_covered": self.topics_covered
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TutorSessionState":
        """Create state from dictionary (for deserialization)."""
        return cls(
            session_id=data["session_id"],
            student_id=data["student_id"],
            course_id=data["course_id"],
            messages=data.get("messages", []),
            current_topic=data.get("current_topic"),
            mastery_snapshot=data.get("mastery_snapshot", {}),
            session_goal=data.get("session_goal"),
            topics_covered=data.get("topics_covered", [])
        )
