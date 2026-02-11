"""Embedding generation using Z.AI or compatible OpenAI API."""

from typing import List

from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel

from ..core.config import Settings, get_settings


class EmbeddingConfig(BaseModel):
    """Configuration for embeddings."""
    model: str
    dimensions: int
    batch_size: int = 100


class EmbeddingService:
    """Service for generating embeddings using an OpenAI-compatible backend."""

    def __init__(self, settings: Settings):
        """Initialize the embedding service configuration."""
        self.settings = settings
        api_key = settings.EMBEDDINGS_API_KEY
        base = (settings.EMBEDDINGS_BASE_URL or "").lower()
        if not api_key and ("127.0.0.1" in base or "localhost" in base):
            api_key = "lm-studio"

        # OpenAI-compatible embeddings API (LM Studio, cloud providers, etc.)
        self.embeddings = OpenAIEmbeddings(
            base_url=settings.EMBEDDINGS_BASE_URL,
            api_key=api_key,
            model=settings.EMBEDDINGS_MODEL,
            # LM Studio expects raw strings for /v1/embeddings.
            # LangChain's tiktoken path may send token arrays that LM Studio rejects.
            tiktoken_enabled=False,
            check_embedding_ctx_length=False,
        )

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each as list of floats)
        """
        return await self.embeddings.aembed_documents(texts)

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text string to embed

        Returns:
            Embedding vector as list of floats
        """
        return self.embeddings.embed_query(text)


# Singleton instance
_embedding_service: EmbeddingService | None = None


def get_embeddings() -> EmbeddingService:
    """Get or create the singleton embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        settings = get_settings()
        _embedding_service = EmbeddingService(settings)
    return _embedding_service
