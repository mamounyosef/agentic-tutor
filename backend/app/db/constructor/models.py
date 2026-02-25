"""Database models for the Constructor workflow.

This module defines SQLAlchemy ORM models for:
- Creators (course creators)
- Courses
- Modules (course divisions like weeks/sections)
- Units (learning units within modules)
- Topics (learning topics within units)
- Materials (course content files)
- Quizzes (quiz containers)
- Quiz Questions (individual questions within quizzes)
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
    Numeric,
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
    modules = relationship("Module", back_populates="course", cascade="all, delete-orphan", order_by="Module.order_index")
    materials = relationship("Material", back_populates="course", cascade="all, delete-orphan")
    quizzes = relationship("Quiz", back_populates="course", cascade="all, delete-orphan")
    quiz_questions = relationship("QuizQuestion", back_populates="course", cascade="all, delete-orphan")
    sessions = relationship("ConstructorSession", back_populates="course", cascade="all, delete-orphan")

    # Index for full-text search
    __table_args__ = (
        Index("idx_course_title_desc", "title", "description"),
    )


class Module(Base):
    """Course module model (e.g., Week 1, Foundations, Advanced Topics)."""
    __tablename__ = "modules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False)
    prerequisites = Column(JSON, nullable=True)  # List of module IDs

    # Relationships
    course = relationship("Course", back_populates="modules")
    units = relationship("Unit", back_populates="module", cascade="all, delete-orphan", order_by="Unit.order_index")

    __table_args__ = (
        UniqueConstraint("course_id", "order_index", name="unique_module_order"),
    )


class Unit(Base):
    """Learning unit model within a module - content container."""
    __tablename__ = "units"

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_id = Column(Integer, ForeignKey("modules.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False)
    prerequisites = Column(JSON, nullable=True)  # List of unit IDs

    # Relationships
    module = relationship("Module", back_populates="units")
    topics = relationship("Topic", back_populates="unit", cascade="all, delete-orphan", order_by="Topic.order_index")
    materials = relationship("Material", back_populates="unit")
    quizzes = relationship("Quiz", back_populates="unit", cascade="all, delete-orphan", order_by="Quiz.order_index")

    __table_args__ = (
        UniqueConstraint("module_id", "order_index", name="unique_unit_order"),
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

    __table_args__ = (
        UniqueConstraint("unit_id", "order_index", name="unique_topic_order"),
    )


class Quiz(Base):
    """Quiz model - container for quiz questions within a unit."""
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)  # What this quiz covers
    order_index = Column(Integer, nullable=False)  # Order within the unit
    time_limit_seconds = Column(Integer, nullable=True)  # NULL = no time limit
    passing_score = Column(Numeric(5, 2), default=70.00)  # Percentage needed to pass (0-100)
    max_attempts = Column(Integer, default=3)  # Maximum number of attempts
    is_published = Column(Boolean, default=False, index=True)
    created_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String(50), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())

    # Relationships
    unit = relationship("Unit", back_populates="quizzes")
    course = relationship("Course", back_populates="quizzes")
    questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan", order_by="QuizQuestion.order_index")

    __table_args__ = (
        UniqueConstraint("unit_id", "order_index", name="unique_quiz_order"),
        Index("idx_quiz_published", "is_published"),
    )


class Material(Base):
    """Course material model (PDFs, slides, videos, etc.)."""
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="CASCADE"), nullable=True, index=True)
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
    unit = relationship("Unit")
    course = relationship("Course", back_populates="materials")


class QuizQuestion(Base):
    """Quiz question model - individual questions within a quiz."""
    __tablename__ = "quiz_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True)  # Denormalized for queries
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)  # Denormalized for queries
    question_text = Column(Text, nullable=False)
    question_type = Column(
        Enum("multiple_choice", "true_false", "short_answer", "essay", name="question_type"),
        nullable=False
    )
    options = Column(JSON, nullable=True)  # For multiple choice: [{"text": "Option A", "is_correct": false}]
    correct_answer = Column(Text, nullable=False)
    rubric = Column(Text, nullable=True)  # Grading criteria for open-ended questions
    difficulty = Column(
        Enum("easy", "medium", "hard", name="difficulty"),
        default="medium"
    )
    points_value = Column(Numeric(5, 2), default=1.00)  # Points this question is worth
    order_index = Column(Integer, default=0)  # Order within the quiz
    course_metadata = Column(JSON, nullable=True)  # Tags, concepts tested, etc.
    created_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())

    # Vector embedding for similarity search
    embedding_id = Column(String(255), nullable=True)  # Reference to vector DB

    # Relationships
    quiz = relationship("Quiz", back_populates="questions")
    unit = relationship("Unit")
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
