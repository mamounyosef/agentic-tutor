"""LLM Client Factory for Z.AI integration.

Provides a factory function to create LLM clients configured for Z.AI's
OpenAI-compatible API.
"""

from typing import Optional

from langchain_openai import ChatOpenAI

from ...core.config import get_settings


def get_llm(
    temperature: Optional[float] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    streaming: bool = False,
) -> ChatOpenAI:
    """
    Get a configured LLM client for Z.AI.

    Args:
        temperature: Override default temperature (0.0-1.0)
        model: Override default model name
        max_tokens: Override default max tokens
        streaming: Enable streaming responses

    Returns:
        Configured ChatOpenAI instance

    Example:
        >>> llm = get_llm(temperature=0.5)
        >>> response = await llm.ainvoke("Hello!")
    """
    settings = get_settings()

    return ChatOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        model=model or settings.LLM_MODEL,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
        max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
        streaming=streaming,
    )


def get_llm_for_structured_output(
    schema: type,
    temperature: Optional[float] = None,
    model: Optional[str] = None,
) -> ChatOpenAI:
    """
    Get an LLM configured for structured JSON output.

    Args:
        schema: Pydantic model class for structured output
        temperature: Override default temperature
        model: Override default model name

    Returns:
        ChatOpenAI instance with structured output configured
    """
    llm = get_llm(temperature=temperature, model=model)
    return llm.with_structured_output(schema)
