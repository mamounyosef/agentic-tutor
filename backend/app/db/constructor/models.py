"""Database models for the Constructor workflow.

This module defines SQLAlchemy ORM models for:
- Creators (course creators)
- Courses
- Units
- Topics
- Materials
- Quiz Questions
- Constructor Sessions
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class Creator(Base):
    """Course creator user model."""
    __tablename__ = "creators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    created_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String(50), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())
    settings = Column(JSON, nullable=True)

    # Relationships
    courses = relationship("Course", back_populates="creator", cascade="all, delete-orphan")


class Course(Base):
    """Course model for storing course information."""
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    difficulty = Column(Enum("beginner", "intermediate", "advanced", name="course_difficulty"), default="beginner")
    is_published = Column(Boolean, default=False, index=True)
    created_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String(50), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())
    course_metadata = Column(JSON, nullable=True)

    # Relationships
    creator = relationship("Creator", back_populates="courses")
    units = relationship("Unit", back_populates="course", cascade="all, delete-orphan", order_by="Unit.order_index")
    materials = relationship("Material", back_populates="course", cascade="all, delete-orphan")
    quiz_questions = relationship("QuizQuestion", back_populates="course", cascade="all, delete-orphan")
    sessions = relationship("ConstructorSession", back_populates="course", cascade="all, delete-orphan")

    # Index for full-text search
    __table_args__ = (
        Index("idx_course_title_desc", "title", "description"),
    )


class Unit(Base):
    """Course unit model."""
    __tablename__ = "units"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False)
    prerequisites = Column(JSON, nullable=True)  # List of unit IDs

    # Relationships
    course = relationship("Course", back_populates="units")
    topics = relationship("Topic", back_populates="unit", cascade="all, delete-orphan", order_by="Topic.order_index")

    __table_args__ = (
        UniqueConstraint("course_id", "order_index", name="unique_unit_order"),
    )


class Topic(Base):
    """Learning topic model."""
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    content_summary = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False)

    # Relationships
    unit = relationship("Unit", back_populates="topics")
    materials = relationship("Material", back_populates="topic", cascade="all, delete-orphan")
    quiz_questions = relationship("QuizQuestion", back_populates="topic", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("unit_id", "order_index", name="unique_topic_order"),
    )


class Material(Base):
    """Course material model (PDFs, slides, videos, etc.)."""
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    material_type = Column(
        Enum("pdf", "ppt", "pptx", "docx", "video", "text", "other", name="material_type"),
        nullable=False
    )
    file_path = Column(String(512), nullable=False)
    original_filename = Column(String(255), nullable=True)
    course_metadata = Column(JSON, nullable=True)
    uploaded_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())

    # Processing status
    processing_status = Column(
        Enum("pending", "processing", "completed", "error", name="processing_status"),
        default="pending"
    )
    chunks_count = Column(Integer, default=0)

    # Relationships
    topic = relationship("Topic", back_populates="materials")
    course = relationship("Course", back_populates="materials")


class QuizQuestion(Base):
    """Quiz question model."""
    __tablename__ = "quiz_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    question_type = Column(
        Enum("multiple_choice", "true_false", "short_answer", "essay", name="question_type"),
        nullable=False
    )
    options = Column(JSON, nullable=True)  # List of {text, value}
    correct_answer = Column(Text, nullable=False)
    rubric = Column(Text, nullable=True)
    difficulty = Column(
        Enum("easy", "medium", "hard", name="difficulty"),
        default="medium"
    )
    course_metadata = Column(JSON, nullable=True)
    created_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())

    # Vector embedding for similarity search
    embedding_id = Column(String(255), nullable=True)  # Reference to vector DB

    # Relationships
    topic = relationship("Topic", back_populates="quiz_questions")
    course = relationship("Course", back_populates="quiz_questions")


class ConstructorSession(Base):
    """Constructor session model for tracking course construction."""
    __tablename__ = "constructor_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(Integer, ForeignKey("creators.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True)
    started_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())
    completed_at = Column(String(50), nullable=True)
    status = Column(
        Enum("in_progress", "completed", "abandoned", name="session_status"),
        default="in_progress"
    )
    messages_json = Column(JSON, nullable=True)  # Conversation history

    # Progress tracking
    phase = Column(String(50), default="welcome")  # Current construction phase
    files_uploaded = Column(Integer, default=0)
    files_processed = Column(Integer, default=0)
    topics_created = Column(Integer, default=0)
    questions_created = Column(Integer, default=0)

    # Relationships
    course = relationship("Course", back_populates="sessions")
    creator = relationship("Creator")
