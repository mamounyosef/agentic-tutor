"""Authentication API endpoints for both creators and students."""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr

from sqlalchemy import select

from ....core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)
from ....core.config import Settings, get_settings
from ....db.constructor.models import Creator
from ....db.tutor.models import Student
from ....db.base import get_constructor_session, get_tutor_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# OAuth2 scheme for JWT bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")


# ==============================================================================
# Pydantic Models
# ==============================================================================

class CreatorRegister(BaseModel):
    """Creator registration schema."""
    email: EmailStr
    password: str
    full_name: str


class StudentRegister(BaseModel):
    """Student registration schema."""
    email: EmailStr
    password: str
    full_name: str
    age: int | None = None
    gender: str | None = None
    education_level: str | None = None


class CreatorLogin(BaseModel):
    """Creator login schema."""
    email: EmailStr
    password: str


class StudentLogin(BaseModel):
    """Student login schema."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    user_type: str  # "creator" or "student"
    user_id: int


class UserResponse(BaseModel):
    """User information response."""
    id: int
    email: str
    full_name: str
    user_type: str


# ==============================================================================
# Authentication Dependencies
# ==============================================================================

async def get_current_creator(
    token: str = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings)
) -> Creator:
    """Get the current authenticated creator from JWT token."""
    from ....core.security import verify_access_token

    payload = verify_access_token(token)
    if not payload or payload.get("user_type") != "creator":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

    creator_id = payload.get("creator_id")
    if not creator_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    async with get_constructor_session() as session:
        result = await session.execute(
            select(Creator).where(Creator.id == creator_id)
        )
        creator = result.scalar_one_or_none()

        if not creator:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Creator not found"
            )

        return creator


async def get_current_student(
    token: str = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings)
) -> Student:
    """Get the current authenticated student from JWT token."""
    from ....core.security import verify_access_token
    from sqlalchemy import select

    payload = verify_access_token(token)
    if not payload or payload.get("user_type") != "student":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

    student_id = payload.get("student_id")
    if not student_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    async with get_tutor_session() as session:
        result = await session.execute(
            select(Student).where(Student.id == student_id)
        )
        student = result.scalar_one_or_none()

        if not student:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Student not found"
            )

        return student


async def get_optional_creator(
    token: Optional[str] = None,
    settings: Settings = Depends(get_settings)
) -> Creator | None:
    """Get the current authenticated creator, or None if no token provided."""
    if not token:
        return None
    try:
        return await get_current_creator(token, settings)
    except HTTPException:
        return None


async def get_optional_student(
    token: Optional[str] = None,
    settings: Settings = Depends(get_settings)
) -> Student | None:
    """Get the current authenticated student, or None if no token provided."""
    if not token:
        return None
    try:
        return await get_current_student(token, settings)
    except HTTPException:
        return None


# ==============================================================================
# Helper Functions
# ==============================================================================

async def authenticate_creator(
    email: str,
    password: str,
    settings: Settings
) -> Optional[Creator]:
    """Authenticate a course creator."""

    async with get_constructor_session() as session:
        result = await session.execute(
            select(Creator).where(Creator.email == email)
        )
        creator = result.scalar_one_or_none()

        if creator and verify_password(password, creator.password_hash):
            return creator

    return None


async def authenticate_student(
    email: str,
    password: str,
    settings: Settings
) -> Optional[Student]:
    """Authenticate a student."""

    async with get_tutor_session() as session:
        result = await session.execute(
            select(Student).where(Student.email == email)
        )
        student = result.scalar_one_or_none()

        if student and verify_password(password, student.password_hash):
            return student

    return None


# ==============================================================================
# Creator Authentication Endpoints
# ==============================================================================

@router.post("/creator/register", status_code=status.HTTP_201_CREATED)
async def register_creator(
    user_in: CreatorRegister,
    settings: Settings = Depends(get_settings)
) -> TokenResponse:
    """Register a new course creator."""

    async with get_constructor_session() as session:
        # Check if email already exists
        existing = await session.execute(
            select(Creator).where(Creator.email == user_in.email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Create new creator
        creator = Creator(
            email=user_in.email,
            password_hash=get_password_hash(user_in.password),
            full_name=user_in.full_name,
        )

        session.add(creator)
        await session.commit()
        await session.refresh(creator)

        # Create JWT token
        token_data = {
            "sub": creator.email,
            "user_type": "creator",
            "creator_id": creator.id
        }
        access_token = create_access_token(token_data)

        logger.info(f"New creator registered: {creator.email}")

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user_type="creator"
        )


@router.post("/creator/login")
async def login_creator(
    user_in: CreatorLogin,
    settings: Settings = Depends(get_settings)
) -> TokenResponse:
    """Authenticate a course creator."""
    creator = await authenticate_creator(user_in.email, user_in.password, settings)

    if not creator:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    # Create JWT token
    token_data = {
        "sub": creator.email,
        "user_type": "creator",
        "creator_id": creator.id
    }
    access_token = create_access_token(token_data)

    logger.info(f"Creator logged in: {creator.email}")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_type="creator"
    )


@router.get("/creator/me", response_model=UserResponse)
async def get_creator_me(
    current_creator: Creator = Depends(get_current_creator)
) -> UserResponse:
    """Get current creator information."""
    return UserResponse(
        id=current_creator.id,
        email=current_creator.email,
        full_name=current_creator.full_name,
        user_type="creator"
    )


# ==============================================================================
# Student Authentication Endpoints
# ==============================================================================

@router.post("/student/register", status_code=status.HTTP_201_CREATED)
async def register_student(
    user_in: StudentRegister,
    settings: Settings = Depends(get_settings)
) -> TokenResponse:
    """Register a new student."""

    async with get_tutor_session() as session:
        # Check if email already exists
        existing = await session.execute(
            select(Student).where(Student.email == user_in.email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Create new student
        student = Student(
            email=user_in.email,
            password_hash=get_password_hash(user_in.password),
            full_name=user_in.full_name,
            age=user_in.age,
            gender=user_in.gender,
            education_level=user_in.education_level,
        )

        session.add(student)
        await session.commit()
        await session.refresh(student)

        # Create student profile
        from ....db.tutor.models import StudentProfile

        profile = StudentProfile(
            student_id=student.id,
            session_length_preference=30,
            total_sessions=0,
            total_study_time=0,
        )
        session.add(profile)
        await session.commit()

        # Create JWT token
        token_data = {
            "sub": student.email,
            "user_type": "student",
            "student_id": student.id
        }
        access_token = create_access_token(token_data)

        logger.info(f"New student registered: {student.email}")

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user_type="student"
        )


@router.post("/student/login")
async def login_student(
    user_in: StudentLogin,
    settings: Settings = Depends(get_settings)
) -> TokenResponse:
    """Authenticate a student."""
    student = await authenticate_student(user_in.email, user_in.password, settings)

    if not student:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    # Create JWT token
    token_data = {
        "sub": student.email,
        "user_type": "student",
        "student_id": student.id
    }
    access_token = create_access_token(token_data)

    logger.info(f"Student logged in: {student.email}")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_type="student"
    )


@router.get("/student/me", response_model=UserResponse)
async def get_student_me(
    current_student: Student = Depends(get_current_student)
) -> UserResponse:
    """Get current student information."""
    return UserResponse(
        id=current_student.id,
        email=current_student.email,
        full_name=current_student.full_name,
        user_type="student"
    )
