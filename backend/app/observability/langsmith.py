"""LangSmith tracing setup and helper utilities."""

import logging
import os
from typing import Any, Dict, Iterable, Optional

from app.core.config import Settings

logger = logging.getLogger(__name__)


def initialize_langsmith(settings: Settings) -> bool:
    """
    Initialize LangSmith tracing environment.

    Sets the LANGCHAIN_* environment variables that LangChain/LangGraph
    use to automatically enable tracing for all agents and tools.

    Returns:
        True when tracing is enabled and API key is present, else False.
    """
    tracing_requested = bool(settings.LANGCHAIN_TRACING_V2)
    has_api_key = bool(settings.LANGCHAIN_API_KEY.strip())
    tracing_enabled = tracing_requested and has_api_key

    # Set the standard LangChain environment variables
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if tracing_enabled else "false"

    if settings.LANGCHAIN_API_KEY:
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
    if settings.LANGCHAIN_ENDPOINT:
        os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT
    if settings.LANGCHAIN_PROJECT:
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT

    if tracing_enabled:
        logger.info(
            "LangSmith tracing enabled (project=%s, endpoint=%s)",
            settings.LANGCHAIN_PROJECT,
            settings.LANGCHAIN_ENDPOINT,
        )
    else:
        logger.info("LangSmith tracing disabled")

    return tracing_enabled


def build_trace_config(
    thread_id: str,
    tags: Optional[Iterable[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a LangChain/LangGraph runnable config with tags/metadata."""
    config = dict(config or {})

    existing_configurable = dict(config.get("configurable", {}))
    existing_tags = list(config.get("tags", []))
    existing_metadata = dict(config.get("metadata", {}))

    if tags:
        existing_tags.extend(list(tags))
    if metadata:
        existing_metadata.update(metadata)

    config["configurable"] = {**existing_configurable, "thread_id": thread_id}
    if existing_tags:
        config["tags"] = existing_tags
    if existing_metadata:
        config["metadata"] = existing_metadata

    return config
