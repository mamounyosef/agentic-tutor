"""Database models for the Tutor workflow.

This module defines SQLAlchemy ORM models for:
- Students
- Enrollments
- Mastery
- Quiz Attempts
- Tutor Sessions
- Tutor Interactions
- Student Profiles
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

from ....db.base import Base


class Student(Base):
    """Student user model."""
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    age = Column(Integer, nullable=True)
    gender = Column(Enum("male", "female", "other", "prefer_not_to_say", name="gender"), nullable=True)
    education_level = Column(
        Enum("high_school", "undergraduate", "graduate", "postgraduate", "other", name="education_level"),
        nullable=True
    )
    created_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String(50), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())
    settings = Column(JSON, nullable=True)

    # Relationships
    enrollments = relationship("Enrollment", back_populates="student", cascade="all, delete-orphan")
    mastery_records = relationship("Mastery", back_populates="student", cascade="all, delete-orphan")
    quiz_attempts = relationship("QuizAttempt", back_populates="student", cascade="all, delete-orphan")
    tutor_sessions = relationship("TutorSession", back_populates="student", cascade="all, delete-orphan")
    profile = relationship("StudentProfile", back_populates="student", uselist=False, cascade="all, delete-orphan")


class Enrollment(Base):
    """Student enrollment in a course."""
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(Integer, nullable=False, index=True)  # References Constructor DB course
    enrolled_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())
    status = Column(
        Enum("active", "completed", "dropped", name="enrollment_status"),
        default="active"
    )
    completion_percentage = Column(Float, default=0.0)
    last_accessed_at = Column(String(50), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())

    # Relationships
    student = relationship("Student", back_populates="enrollments")

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="unique_enrollment"),
    )


class Mastery(Base):
    """Student mastery level per topic."""
    __tablename__ = "mastery"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_id = Column(Integer, nullable=False, index=True)  # References Constructor DB topic
    score = Column(Float, default=0.0, nullable=False)  # 0.0 to 1.0
    attempts_count = Column(Integer, default=0, nullable=False)
    last_updated = Column(String(50), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())
    streak_count = Column(Integer, default=0, nullable=False)

    # Relationships
    student = relationship("Student", back_populates="mastery_records")

    __table_args__ = (
        UniqueConstraint("student_id", "topic_id", name="unique_mastery"),
        Index("idx_student_mastery", "student_id", "score"),
    )


class QuizAttempt(Base):
    """Student quiz attempt records."""
    __tablename__ = "quiz_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(Integer, nullable=False, index=True)  # References Constructor DB quiz_question
    user_answer = Column(Text, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    score = Column(Float, default=0.0, nullable=False)  # 0.0 to 1.0
    feedback_json = Column(JSON, nullable=True)
    attempted_at = Column(String(50), default=lambda: datetime.utcnow().isoformat(), index=True)
    time_spent_seconds = Column(Integer, nullable=True)

    # Relationships
    student = relationship("Student", back_populates="quiz_attempts")


class TutorSession(Base):
    """Tutoring session records."""
    __tablename__ = "tutor_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(Integer, nullable=False, index=True)  # References Constructor DB course
    started_at = Column(String(50), default=lambda: datetime.utcnow().isoformat(), index=True)
    ended_at = Column(String(50), nullable=True)
    topics_covered = Column(JSON, nullable=True)  # List of topic IDs
    initial_mastery = Column(JSON, nullable=True)  # Snapshot at start
    final_mastery = Column(JSON, nullable=True)  # Snapshot at end
    session_goal = Column(String(255), nullable=True)
    session_summary = Column(Text, nullable=True)

    # Relationships
    student = relationship("Student", back_populates="tutor_sessions")
    interactions = relationship("TutorInteraction", back_populates="session", cascade="all, delete-orphan")


class TutorInteraction(Base):
    """Individual interaction records within a tutoring session."""
    __tablename__ = "tutor_interactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("tutor_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    interaction_type = Column(
        Enum("question", "explanation", "hint", "quiz", "feedback", "review", name="interaction_type"),
        nullable=False
    )
    content = Column(JSON, nullable=False)  # The interaction content
    ai_action = Column(String(100), nullable=True)  # What the AI did
    mastery_snapshot = Column(JSON, nullable=True)  # Mastery at this point
    timestamp = Column(String(50), default=lambda: datetime.utcnow().isoformat(), index=True)

    # Relationships
    session = relationship("TutorSession", back_populates="interactions")


class StudentProfile(Base):
    """Student profile with learning preferences and statistics."""
    __tablename__ = "student_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, unique=True)
    learning_style = Column(String(50), nullable=True)  # visual, auditory, kinesthetic, etc.
    preferred_difficulty = Column(String(20), nullable=True)
    session_length_preference = Column(Integer, default=30)  # Preferred session length in minutes
    total_sessions = Column(Integer, default=0)
    total_study_time = Column(Integer, default=0)  # Total study time in seconds
    last_active_at = Column(String(50), default=lambda: datetime.utcnow().isoformat(), onupdate=lambda: datetime.utcnow().isoformat())

    # Relationships
    student = relationship("Student", back_populates="profile")
