"""WebSocket manager for streaming token-by-token responses.

This module provides WebSocket connection management for real-time
streaming of LLM responses to both Constructor and Tutor workflows.
"""

import json
import logging
from typing import Dict, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect

from langchain_core.messages import BaseMessage, AIMessage, HumanMessage

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for streaming responses.

    Each session has its own WebSocket connection for real-time updates.
    """

    def __init__(self):
        """Initialize the connection manager."""
        # Active WebSocket connections by session_id
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """
        Accept and register a new WebSocket connection.

        Args:
            session_id: Unique session identifier
            websocket: The WebSocket connection
        """
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected for session: {session_id}")

    def disconnect(self, session_id: str) -> None:
        """
        Remove a WebSocket connection.

        Args:
            session_id: Session identifier to disconnect
        """
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket disconnected for session: {session_id}")

    async def send_message(
        self,
        session_id: str,
        message: str,
        message_type: str = "response",
        metadata: Optional[Dict] = None,
    ) -> bool:
        """
        Send a message to a specific session.

        Args:
            session_id: Session identifier
            message: The message content
            message_type: Type of message (response, error, status, etc.)
            metadata: Optional metadata to include

        Returns:
            True if message was sent, False if session not found
        """
        if session_id not in self.active_connections:
            logger.warning(f"No active connection for session: {session_id}")
            return False

        websocket = self.active_connections[session_id]
        payload = {
            "type": message_type,
            "content": message,
            "metadata": metadata or {},
        }

        try:
            await websocket.send_json(payload)
            return True
        except Exception as e:
            logger.error(f"Error sending message to session {session_id}: {e}")
            self.disconnect(session_id)
            return False

    async def send_token(
        self,
        session_id: str,
        token: str,
        is_first: bool = False,
        is_last: bool = False,
    ) -> bool:
        """
        Send a single token for streaming responses.

        Args:
            session_id: Session identifier
            token: The token content
            is_first: Whether this is the first token
            is_last: Whether this is the last token

        Returns:
            True if token was sent, False otherwise
        """
        return await self.send_message(
            session_id,
            token,
            message_type="token",
            metadata={"is_first": is_first, "is_last": is_last},
        )

    async def send_status(
        self,
        session_id: str,
        status: str,
        progress: Optional[float] = None,
        phase: Optional[str] = None,
    ) -> bool:
        """
        Send a status update.

        Args:
            session_id: Session identifier
            status: Status message
            progress: Optional progress percentage (0-1)
            phase: Optional current phase

        Returns:
            True if status was sent, False otherwise
        """
        return await self.send_message(
            session_id,
            status,
            message_type="status",
            metadata={"progress": progress, "phase": phase},
        )

    async def send_error(
        self,
        session_id: str,
        error: str,
        error_code: Optional[str] = None,
    ) -> bool:
        """
        Send an error message.

        Args:
            session_id: Session identifier
            error: Error message
            error_code: Optional error code

        Returns:
            True if error was sent, False otherwise
        """
        return await self.send_message(
            session_id,
            error,
            message_type="error",
            metadata={"error_code": error_code},
        )

    async def broadcast_to_session(
        self,
        session_id: str,
        payload: Dict,
    ) -> bool:
        """
        Send a raw JSON payload to a session.

        Args:
            session_id: Session identifier
            payload: The JSON payload to send

        Returns:
            True if payload was sent, False otherwise
        """
        if session_id not in self.active_connections:
            return False

        websocket = self.active_connections[session_id]
        try:
            await websocket.send_json(payload)
            return True
        except Exception as e:
            logger.error(f"Error broadcasting to session {session_id}: {e}")
            self.disconnect(session_id)
            return False

    def is_connected(self, session_id: str) -> bool:
        """
        Check if a session has an active connection.

        Args:
            session_id: Session identifier

        Returns:
            True if connected, False otherwise
        """
        return session_id in self.active_connections

    def get_active_sessions(self) -> Set[str]:
        """
        Get all currently active session IDs.

        Returns:
            Set of active session IDs
        """
        return set(self.active_connections.keys())


# Global connection manager instance
manager = ConnectionManager()


# =============================================================================
# Streaming Utilities
# =============================================================================

async def stream_ai_message(
    session_id: str,
    message: AIMessage,
    manager: ConnectionManager = manager,
) -> None:
    """
    Stream an AI message token by token.

    Args:
        session_id: Session identifier
        message: The AI message to stream
        manager: Connection manager instance
    """
    content = message.content if isinstance(message.content, str) else str(message.content)

    # Send tokens one at a time (or in small chunks for efficiency)
    # For true token-by-token, we'd need to use the LLM's streaming API
    # This is a simplified version that chunks by characters
    chunk_size = 10  # Adjust based on desired granularity

    for i in range(0, len(content), chunk_size):
        chunk = content[i:i + chunk_size]
        is_first = (i == 0)
        is_last = (i + chunk_size >= len(content))

        await manager.send_token(
            session_id,
            chunk,
            is_first=is_first,
            is_last=is_last,
        )


async def stream_langgraph_events(
    session_id: str,
    events,
    manager: ConnectionManager = manager,
) -> None:
    """
    Stream LangGraph events to a WebSocket session.

    Args:
        session_id: Session identifier
        events: Async iterator of LangGraph events
        manager: Connection manager instance
    """
    async for event in events:
        # Extract node name and output
        node_name = None
        output = None

        if isinstance(event, tuple) and len(event) == 2:
            node_name, output = event
        elif isinstance(event, dict):
            # Try to extract node and output from dict
            node_name = event.get("node") or event.get("name")
            output = event.get("output") or event

        # Send status update for node transitions
        if node_name:
            await manager.send_status(
                session_id,
                f"Processing: {node_name}",
                phase=node_name,
            )

        # Extract and stream any AI messages
        if output:
            if isinstance(output, dict):
                messages = output.get("messages", [])
            elif isinstance(output, list):
                messages = output
            else:
                messages = [output]

            for msg in messages:
                if isinstance(msg, AIMessage):
                    await stream_ai_message(session_id, msg, manager)
                elif isinstance(msg, dict) and msg.get("type") == "ai":
                    content = msg.get("content", "")
                    if content:
                        await manager.send_token(
                            session_id,
                            content,
                            is_first=True,
                            is_last=True,
                        )
