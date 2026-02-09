"""Configuration settings for Agentic Tutor."""

import secrets
from functools import lru_cache
from typing import List

from pydantic import Field, EmailStr
from pydantic_settings import BaseSettings, SettingsConfig


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfig(
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
        default=secrets.token_urlsafe(32),
        min_length=32,
        description="Secret key for JWT encoding"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Database - Constructor
    CONSTRUCTOR_DB_URL: str = Field(
        default="mysql+pymysql://user:password@localhost:3306/agentic_tutor_constructor"
    )

    # Database - Tutor
    TUTOR_DB_URL: str = Field(
        default="mysql+pymysql://user:password@localhost:3306/agentic_tutor_tutor"
    )

    # Database Pool Settings
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    # Z.AI LLM
    LLM_BASE_URL: str = "https://api.z.ai/api/paas/v4/"
    LLM_API_KEY: str = Field(default="", description="Z.AI API key")
    LLM_MODEL: str = "glm-4.7"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 4096

    # Embeddings
    EMBEDDINGS_BASE_URL: str = "https://api.z.ai/api/paas/v4/"
    EMBEDDINGS_API_KEY: str = Field(default="", description="Z.AI API key for embeddings")
    EMBEDDINGS_MODEL: str = "embedding-model"
    EMBEDDINGS_DIMENSIONS: int = 1536

    # Vector Database - ChromaDB
    CONSTRUCTOR_VECTOR_DB_PATH: str = "./data/vector_db/constructor"
    STUDENT_VECTOR_DB_PATH: str = "./data/vector_db/students"
    COURSE_VECTOR_DB_PATH: str = "./data/vector_db/courses"
    CHROMA_COLLECTION_CHUNK_SIZE: int = 1000
    CHROMA_COLLECTION_OVERLAP: int = 200

    # Checkpointers
    CONSTRUCTOR_CHECKPOINT_PATH: str = "./checkpoints/constructor"
    TUTOR_CHECKPOINT_PATH: str = "./checkpoints/tutor"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # File Storage
    UPLOAD_DIR: str = "./uploads/materials"
    MAX_UPLOAD_SIZE: int = 10485760  # 10MB in bytes
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".ppt", ".pptx", ".doc", ".docx", ".txt"]

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"

    # Course Settings
    DEFAULT_DIFFICULTY: str = "beginner"
    DEFAULT_SESSION_LENGTH: int = 30  # minutes
    MASTERY_MIN_SCORE: float = 0.7
    SPACED_REPETITION_DAYS: int = 7


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# For convenience
settings = get_settings()
