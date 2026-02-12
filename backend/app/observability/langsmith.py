"""LangSmith tracing setup and helper utilities."""

import logging
import os
from typing import Any, Dict, Iterable, Optional

from app.core.config import Settings

logger = logging.getLogger(__name__)


def initialize_langsmith(settings: Settings) -> bool:
    """
    Initialize LangSmith tracing environment.

    Returns:
        True when tracing is enabled and API key is present, else False.
    """
    tracing_requested = bool(settings.LANGSMITH_TRACING)
    has_api_key = bool(settings.LANGSMITH_API_KEY.strip())
    tracing_enabled = tracing_requested and has_api_key

    os.environ["LANGSMITH_TRACING"] = "true" if tracing_requested else "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if tracing_enabled else "false"

    if settings.LANGSMITH_API_KEY:
        os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
        # Backward-compatible env names used by some LangChain integrations.
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    if settings.LANGSMITH_ENDPOINT:
        os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
        os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    if settings.LANGSMITH_PROJECT:
        os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
    if settings.LANGSMITH_WORKSPACE_ID:
        os.environ["LANGSMITH_WORKSPACE_ID"] = settings.LANGSMITH_WORKSPACE_ID

    if tracing_enabled:
        logger.info(
            "LangSmith tracing enabled (project=%s, endpoint=%s)",
            settings.LANGSMITH_PROJECT,
            settings.LANGSMITH_ENDPOINT,
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
