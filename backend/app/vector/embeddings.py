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
    """Service for generating embeddings using Z.AI (OpenAI-compatible)."""

    def __init__(self, settings: Settings):
        """Initialize the embedding service with Z.AI configuration."""
        self.settings = settings

        # Z.AI uses OpenAI-compatible API
        self.embeddings = OpenAIEmbeddings(
            base_url=settings.EMBEDDINGS_BASE_URL,
            api_key=settings.EMBEDDINGS_API_KEY,
            model=settings.EMBEDDINGS_MODEL,
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
