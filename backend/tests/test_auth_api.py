"""
Test authentication API endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAuthEndpoints:
    """Test authentication endpoints for both Constructor and Student workflows."""

    # ========== CONSTRUCTOR AUTH TESTS ==========

    async def test_register_creator_success(self, async_client: AsyncClient):
        """Test successful creator registration."""
        response = await async_client.post(
            "/api/v1/auth/constructor/register",
            json={
                "email": "new_creator@example.com",
                "password": "securepass123",
                "full_name": "New Creator"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "creator_id" in data

    async def test_register_creator_duplicate_email(self, async_client: AsyncClient):
        """Test registration with duplicate email fails."""
        # First registration
        await async_client.post(
            "/api/v1/auth/constructor/register",
            json={
                "email": "duplicate@example.com",
                "password": "pass123",
                "full_name": "First User"
            }
        )

        # Duplicate registration
        response = await async_client.post(
            "/api/v1/auth/constructor/register",
            json={
                "email": "duplicate@example.com",
                "password": "pass456",
                "full_name": "Second User"
            }
        )
        assert response.status_code == 400

    async def test_register_creator_missing_fields(self, async_client: AsyncClient):
        """Test registration with missing fields fails."""
        response = await async_client.post(
            "/api/v1/auth/constructor/register",
            json={
                "email": "incomplete@example.com"
            }
        )
        assert response.status_code == 422

    async def test_login_creator_success(self, async_client: AsyncClient):
        """Test successful creator login."""
        # Register first
        await async_client.post(
            "/api/v1/auth/constructor/register",
            json={
                "email": "login_test@example.com",
                "password": "loginpass123",
                "full_name": "Login Test"
            }
        )

        # Login
        response = await async_client.post(
            "/api/v1/auth/constructor/login",
            data={
                "username": "login_test@example.com",
                "password": "loginpass123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    async def test_login_creator_wrong_password(self, async_client: AsyncClient):
        """Test login with wrong password fails."""
        # Register first
        await async_client.post(
            "/api/v1/auth/constructor/register",
            json={
                "email": "wrong_pass@example.com",
                "password": "correctpass",
                "full_name": "Wrong Pass Test"
            }
        )

        # Login with wrong password
        response = await async_client.post(
            "/api/v1/auth/constructor/login",
            data={
                "username": "wrong_pass@example.com",
                "password": "wrongpass"
            }
        )
        assert response.status_code == 401

    async def test_get_creator_me_authenticated(self, async_client: AsyncClient, auth_headers_creator: dict):
        """Test getting creator profile when authenticated."""
        response = await async_client.get(
            "/api/v1/auth/constructor/me",
            headers=auth_headers_creator
        )
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert "full_name" in data

    async def test_get_creator_me_unauthenticated(self, async_client: AsyncClient):
        """Test getting creator profile without auth fails."""
        response = await async_client.get("/api/v1/auth/constructor/me")
        assert response.status_code == 401

    # ========== STUDENT AUTH TESTS ==========

    async def test_register_student_success(self, async_client: AsyncClient):
        """Test successful student registration."""
        response = await async_client.post(
            "/api/v1/auth/student/register",
            json={
                "email": "new_student@example.com",
                "password": "securepass123",
                "full_name": "New Student",
                "age": 22,
                "gender": "female",
                "education_level": "undergraduate"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "student_id" in data

    async def test_register_student_minimal(self, async_client: AsyncClient):
        """Test student registration with only required fields."""
        response = await async_client.post(
            "/api/v1/auth/student/register",
            json={
                "email": "minimal_student@example.com",
                "password": "pass123",
                "full_name": "Minimal Student"
            }
        )
        assert response.status_code == 200

    async def test_login_student_success(self, async_client: AsyncClient):
        """Test successful student login."""
        # Register first
        await async_client.post(
            "/api/v1/auth/student/register",
            json={
                "email": "student_login@example.com",
                "password": "studentpass123",
                "full_name": "Student Login Test"
            }
        )

        # Login
        response = await async_client.post(
            "/api/v1/auth/student/login",
            data={
                "username": "student_login@example.com",
                "password": "studentpass123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    async def test_get_student_me_authenticated(self, async_client: AsyncClient, auth_headers_student: dict):
        """Test getting student profile when authenticated."""
        response = await async_client.get(
            "/api/v1/auth/student/me",
            headers=auth_headers_student
        )
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert "full_name" in data

    async def test_get_student_me_unauthenticated(self, async_client: AsyncClient):
        """Test getting student profile without auth fails."""
        response = await async_client.get("/api/v1/auth/student/me")
        assert response.status_code == 401

    # ========== CROSS-WORKFLOW TESTS ==========

    async def test_separate_auth_systems(self, async_client: AsyncClient):
        """Test that creator and student auth systems are separate."""
        # Register creator
        creator_response = await async_client.post(
            "/api/v1/auth/constructor/register",
            json={
                "email": "shared_email@example.com",
                "password": "creatorpass",
                "full_name": "Creator"
            }
        )
        assert creator_response.status_code == 200

        # Register student with same email - should work (separate systems)
        student_response = await async_client.post(
            "/api/v1/auth/student/register",
            json={
                "email": "shared_email@example.com",
                "password": "studentpass",
                "full_name": "Student"
            }
        )
        # This should succeed because they're separate systems
        assert student_response.status_code == 200
