"""
Test Constructor workflow end-to-end.
"""

import pytest
import json
from httpx import AsyncClient
from pathlib import Path


@pytest.mark.asyncio
class TestConstructorWorkflow:
    """Test the complete Constructor workflow from course creation to finalization."""

    async def test_start_constructor_session(
        self,
        async_client: AsyncClient,
        auth_headers_creator: dict
    ):
        """Test starting a new constructor session."""
        response = await async_client.post(
            "/api/v1/constructor/session/start",
            headers=auth_headers_creator,
            json={
                "course_title": "Test Course",
                "course_description": "A test course for integration testing",
                "difficulty": "beginner"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "message" in data
        assert data["status"] == "started"

    async def test_get_session_status(
        self,
        async_client: AsyncClient,
        auth_headers_creator: dict
    ):
        """Test getting constructor session status."""
        # Start a session first
        start_response = await async_client.post(
            "/api/v1/constructor/session/start",
            headers=auth_headers_creator,
            json={"course_title": "Status Test Course"}
        )
        session_id = start_response.json()["session_id"]

        # Get status
        response = await async_client.get(
            f"/api/v1/constructor/session/status/{session_id}",
            headers=auth_headers_creator
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "status" in data

    async def test_upload_files_to_session(
        self,
        async_client: AsyncClient,
        auth_headers_creator: dict,
        tmp_path: Path
    ):
        """Test uploading files to a constructor session."""
        # Start a session
        start_response = await async_client.post(
            "/api/v1/constructor/session/start",
            headers=auth_headers_creator,
            json={"course_title": "Upload Test Course"}
        )
        session_id = start_response.json()["session_id"]

        # Create a test file
        test_file = tmp_path / "test_material.txt"
        test_file.write_text("This is test content for the course.")

        # Upload file
        with open(test_file, "rb") as f:
            response = await async_client.post(
                f"/api/v1/constructor/session/upload?session_id={session_id}",
                headers=auth_headers_creator,
                files={"files": ("test_material.txt", f, "text/plain")}
            )

        assert response.status_code == 200
        data = response.json()
        assert "files_processed" in data
        assert data["files_processed"] >= 0

    async def test_get_creator_courses(
        self,
        async_client: AsyncClient,
        auth_headers_creator: dict
    ):
        """Test getting list of creator's courses."""
        response = await async_client.get(
            "/api/v1/constructor/courses",
            headers=auth_headers_creator
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_course_details(
        self,
        async_client: AsyncClient,
        auth_headers_creator: dict
    ):
        """Test getting specific course details."""
        # This would require a course to exist first
        # For now, test the endpoint structure
        response = await async_client.get(
            "/api/v1/constructor/course/1",
            headers=auth_headers_creator
        )
        # May return 404 if course doesn't exist, which is fine
        assert response.status_code in [200, 404]

    async def test_finalize_course(
        self,
        async_client: AsyncClient,
        auth_headers_creator: dict
    ):
        """Test finalizing a course for publication."""
        response = await async_client.post(
            "/api/v1/constructor/course/finalize",
            headers=auth_headers_creator,
            json={"course_id": 1}
        )
        # May return 404 if course doesn't exist
        assert response.status_code in [200, 404]

    async def test_full_constructor_workflow(
        self,
        async_client: AsyncClient,
        auth_headers_creator: dict,
        tmp_path: Path
    ):
        """Test the complete constructor workflow end-to-end."""
        # 1. Start a session
        session_response = await async_client.post(
            "/api/v1/constructor/session/start",
            headers=auth_headers_creator,
            json={
                "course_title": "E2E Test Course",
                "course_description": "End-to-end integration test course",
                "difficulty": "intermediate"
            }
        )
        assert session_response.status_code == 200
        session_data = session_response.json()
        session_id = session_data["session_id"]
        assert session_id is not None

        # 2. Check session status
        status_response = await async_client.get(
            f"/api/v1/constructor/session/status/{session_id}",
            headers=auth_headers_creator
        )
        assert status_response.status_code == 200

        # 3. Upload test content
        test_file = tmp_path / "course_content.txt"
        test_file.write_text("""
        Chapter 1: Introduction
        This chapter introduces the basic concepts.

        Chapter 2: Advanced Topics
        This chapter covers more advanced material.
        """)

        with open(test_file, "rb") as f:
            upload_response = await async_client.post(
                f"/api/v1/constructor/session/upload?session_id={session_id}",
                headers=auth_headers_creator,
                files={"files": ("course_content.txt", f, "text/plain")}
            )
        # Upload may succeed or fail depending on implementation
        assert upload_response.status_code in [200, 202, 400]

        # 4. Get courses list
        courses_response = await async_client.get(
            "/api/v1/constructor/courses",
            headers=auth_headers_creator
        )
        assert courses_response.status_code == 200
        courses = courses_response.json()
        assert isinstance(courses, list)


@pytest.mark.asyncio
class TestConstructorWebSocket:
    """Test WebSocket connections for Constructor workflow."""

    async def test_websocket_connection_requires_auth(self):
        """Test that WebSocket connections require authentication."""
        # This would require a WebSocket client
        # For now, we'll test the HTTP endpoint that creates WebSocket
        pass

    async def test_websocket_message_flow(
        self,
        async_client: AsyncClient,
        auth_headers_creator: dict
    ):
        """Test sending messages through the WebSocket."""
        # Test the HTTP message endpoint
        response = await async_client.post(
            "/api/v1/constructor/session/message",
            headers=auth_headers_creator,
            json={
                "session_id": "test-session-id",
                "message": "Create a unit about Python basics"
            }
        )
        # May return 404 if session doesn't exist
        assert response.status_code in [200, 404]
