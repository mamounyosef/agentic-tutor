"""Authentication API endpoints for both creators and students."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from ..core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)
from ..core.config import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["Authentication"])


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


# ==============================================================================
# Helper Functions
# ==============================================================================

async def authenticate_creator(
    email: str,
    password: str,
    settings: Settings
) -> dict[str, Any] | None:
    """Authenticate a course creator."""
    # TODO: Implement after database models are created
    # This will query the creators table from Constructor DB
    pass


async def authenticate_student(
    email: str,
    password: str,
    settings: Settings
) -> dict[str, Any] | None:
    """Authenticate a student."""
    # TODO: Implement after database models are created
    # This will query the students table from Tutor DB
    pass


# ==============================================================================
# Creator Authentication Endpoints
# ==============================================================================

@router.post("/creator/register", status_code=status.HTTP_201_CREATED)
async def register_creator(
    user_in: CreatorRegister,
    settings: Settings = Depends(get_settings)
) -> TokenResponse:
    """Register a new course creator."""
    # TODO: Implement after database models
    # 1. Check if email exists
    # 2. Hash password
    # 3. Create creator record
    # 4. Return JWT token

    # Placeholder - create a mock token for now
    token_data = {"sub": user_in.email, "user_type": "creator"}
    access_token = create_access_token(token_data)

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
    # TODO: Implement after database models
    # 1. Verify password
    # 2. Create JWT token if valid

    # Placeholder
    token_data = {"sub": user_in.email, "user_type": "creator"}
    access_token = create_access_token(token_data)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
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
    # TODO: Implement after database models
    # 1. Check if email exists
    # 2. Hash password
    # 3. Create student record
    # 4. Create student profile
    # 5. Return JWT token

    # Placeholder
    token_data = {"sub": user_in.email, "user_type": "student"}
    access_token = create_access_token(token_data)

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
    # TODO: Implement after database models
    # 1. Verify password
    # 2. Create JWT token if valid

    # Placeholder
    token_data = {"sub": user_in.email, "user_type": "student"}
    access_token = create_access_token(token_data)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_type="student"
    )
