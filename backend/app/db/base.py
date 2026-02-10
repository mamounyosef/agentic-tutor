"""Database base class and session management.

This module provides:
- SQLAlchemy base class for declarative models
- Database session factory
- Engine management for both Constructor and Tutor databases
"""

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ..core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# =============================================================================
# Constructor Database (Course Creators)
# =============================================================================

_constructor_engine = None
_constructor_session_maker = None


def get_constructor_engine():
    """Get or create the Constructor database engine."""
    global _constructor_engine

    if _constructor_engine is None:
        settings = get_settings()
        _constructor_engine = create_async_engine(
            settings.CONSTRUCTOR_DB_URL,
            echo=settings.DEBUG,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
        )

    return _constructor_engine


def get_constructor_session_maker():
    """Get or create the Constructor session maker."""
    global _constructor_session_maker

    if _constructor_session_maker is None:
        engine = get_constructor_engine()
        _constructor_session_maker = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _constructor_session_maker


@asynccontextmanager
async def get_constructor_session():
    """Get a Constructor database session as an async context manager."""
    session_maker = get_constructor_session_maker()
    async with session_maker() as session:
        yield session


# =============================================================================
# Tutor Database (Students)
# =============================================================================

_tutor_engine = None
_tutor_session_maker = None


def get_tutor_engine():
    """Get or create the Tutor database engine."""
    global _tutor_engine

    if _tutor_engine is None:
        settings = get_settings()
        _tutor_engine = create_async_engine(
            settings.TUTOR_DB_URL,
            echo=settings.DEBUG,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
        )

    return _tutor_engine


def get_tutor_session_maker():
    """Get or create the Tutor session maker."""
    global _tutor_session_maker

    if _tutor_session_maker is None:
        engine = get_tutor_engine()
        _tutor_session_maker = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _tutor_session_maker


@asynccontextmanager
async def get_tutor_session():
    """Get a Tutor database session as an async context manager."""
    session_maker = get_tutor_session_maker()
    async with session_maker() as session:
        yield session


# =============================================================================
# Utility Functions
# =============================================================================


async def init_databases():
    """Initialize all databases (create tables)."""
    from .constructor import models as constructor_models
    from .tutor import models as tutor_models

    # Initialize Constructor database
    constructor_engine = get_constructor_engine()
    async with constructor_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initialize Tutor database
    tutor_engine = get_tutor_engine()
    async with tutor_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@lru_cache()
def get_db_session(db_type: str = "constructor"):
    """
    Get a database session synchronously (for compatibility).

    Note: This is a simplified version. For async operations,
    use the async session generators above.
    """
    settings = get_settings()

    if db_type == "constructor":
        url = settings.CONSTRUCTOR_DB_URL
    else:
        url = settings.TUTOR_DB_URL

    # For sync operations, create a sync engine
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(url)
    Session = sessionmaker(bind=engine)

    return Session()


async def close_all():
    """Close all database connections."""
    global _constructor_engine, _tutor_engine

    if _constructor_engine:
        await _constructor_engine.dispose()
        _constructor_engine = None

    if _tutor_engine:
        await _tutor_engine.dispose()
        _tutor_engine = None

    _constructor_session_maker = None
    _tutor_session_maker = None
