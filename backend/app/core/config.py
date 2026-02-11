"""Configuration settings for Agentic Tutor."""

import secrets
from typing import List

from pydantic import Field, EmailStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "agentic_tutor"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # API
    API_V1_PREFIX: str = "/api/v1"

    # Security
    SECRET_KEY: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        min_length=32,
        description="Secret key for JWT encoding"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Database - Constructor
    CONSTRUCTOR_DB_URL: str = Field(
        default="mysql+aiomysql://user:password@localhost:3306/agentic_tutor_constructor"
    )

    # Database - Tutor
    TUTOR_DB_URL: str = Field(
        default="mysql+aiomysql://user:password@localhost:3306/agentic_tutor_tutor"
    )

    # Database Pool Settings
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    # OpenAI-compatible LLM (LM Studio, Ollama proxy, cloud providers, etc.)
    LLM_BASE_URL: str = "http://127.0.0.1:1234/v1"
    LLM_API_KEY: str = Field(default="", description="API key for OpenAI-compatible LLM backend")
    LLM_MODEL: str = "gemma-3-270m-it"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 4096

    # LangSmith tracing
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str = Field(default="", description="LangSmith API key")
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_PROJECT: str = "agentic-tutor"
    LANGSMITH_WORKSPACE_ID: str = Field(default="", description="Optional LangSmith workspace ID")

    # Embeddings
    EMBEDDINGS_BASE_URL: str = "http://127.0.0.1:1234/v1"
    EMBEDDINGS_API_KEY: str = Field(default="", description="API key for OpenAI-compatible embeddings backend")
    EMBEDDINGS_MODEL: str = "text-embedding-nomic-embed-text-v1.5"
    EMBEDDINGS_DIMENSIONS: int = 768

    # Vector Database - ChromaDB
    CONSTRUCTOR_VECTOR_DB_PATH: str = "./data/vector_db/constructor"
    STUDENT_VECTOR_DB_PATH: str = "./data/vector_db/students"
    COURSE_VECTOR_DB_PATH: str = "./data/vector_db/courses"
    CHROMA_COLLECTION_CHUNK_SIZE: int = 1000
    CHROMA_COLLECTION_OVERLAP: int = 200

    # Checkpointers
    CONSTRUCTOR_CHECKPOINT_PATH: str = "./checkpoints/constructor"
    TUTOR_CHECKPOINT_PATH: str = "./checkpoints/tutor"

    # CORS - Accept comma-separated string from .env
    CORS_ORIGINS: str = "http://localhost:3000"
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_HEADERS: str = "*"

    # File Storage
    UPLOAD_DIR: str = "./uploads/materials"
    UPLOAD_PATH: str = "./uploads"  # Base upload path
    MAX_UPLOAD_SIZE: int = 524288000  # 500MB in bytes (for large courses with videos)
    ALLOWED_EXTENSIONS: str = ".pdf,.ppt,.pptx,.doc,.docx,.txt,.mp4,.mov,.avi,.mkv"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"

    # Course Settings
    DEFAULT_DIFFICULTY: str = "beginner"
    DEFAULT_SESSION_LENGTH: int = 30  # minutes
    MASTERY_MIN_SCORE: float = 0.7
    SPACED_REPETITION_DAYS: int = 7

    # Video Transcription (faster-whisper with GPU optimization)
    TRANSCRIPTION_SERVICE: str = "whisper_local"  # "whisper_local" for GPU, "openai" for API
    TRANSCRIPTION_MODEL_SIZE: str = "base"  # tiny, base, small, medium, large-v2, large-v3
    TRANSCRIPTION_DEVICE: str = "cuda"  # "cuda" for GPU (RTX 4060), "cpu" as fallback
    TRANSCRIPTION_COMPUTE_TYPE: str = "float16"  # float16 for GPU, int8 for CPU, float32 for accuracy
    TRANSCRIPTION_LANGUAGE: str = "auto"  # "auto" for auto-detect or specific language code (e.g., "en", "es")
    # OpenAI API fallback (optional, requires API key)
    TRANSCRIPTION_API_KEY: str = Field(default="", description="OpenAI API key for transcription fallback")
    TRANSCRIPTION_OPENAI_MODEL: str = "whisper-1"

    @property
    def cors_origins_list(self) -> List[str]:
        """Convert CORS_ORIGINS string to a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def cors_allow_headers_list(self) -> List[str]:
        """Convert CORS_ALLOW_HEADERS string to a list.

        Note: "*" is not valid for allow_headers when credentials are enabled.
        We return a list of common headers instead.
        """
        if self.CORS_ALLOW_HEADERS == "*":
            return [
                "accept",
                "accept-language",
                "content-language",
                "content-type",
                "authorization",
                "x-requested-with",
            ]
        return [header.strip() for header in self.CORS_ALLOW_HEADERS.split(",")]

    @property
    def allowed_extensions_list(self) -> List[str]:
        """Convert ALLOWED_EXTENSIONS string to a list."""
        return [ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(",")]


def get_settings() -> Settings:
    """Get settings instance."""
    return Settings()


# For convenience - create fresh instance each time to avoid caching issues
settings = get_settings()
