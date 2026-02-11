"""Base state definitions for LangGraph agents.

Provides base TypedDict classes that can be extended for specific
agent workflows.
"""

from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

from langgraph.graph import add_messages
from pydantic import BaseModel
from typing_extensions import TypedDict


class Message(BaseModel):
    """A single message in the conversation."""

    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: str = ""

    def __init__(self, **data):
        if not data.get("timestamp"):
            data["timestamp"] = datetime.utcnow().isoformat()
        super().__init__(**data)


class BaseAgentState(TypedDict):
    """Base state for all agents.

    All agent states should inherit from or include these common fields.
    """

    # Conversation history - uses LangGraph's add_messages reducer
    messages: Annotated[List[Dict[str, Any]], add_messages]

    # Session identification
    session_id: str

    # Current step in the agent's workflow
    current_step: str

    # Any errors encountered
    errors: List[str]


class AgentResponse(BaseModel):
    """Standard response format for agent invocations."""

    session_id: str
    message: str
    current_step: str
    progress: float = 0.0
    data: Optional[Dict[str, Any]] = None
    errors: List[str] = []


class SubAgentResult(BaseModel):
    """Result from a sub-agent invocation."""

    agent_name: str
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: str = ""
    errors: List[str] = []
