"""
Pytest configuration and fixtures for integration tests.
"""

import os
import sys
import pytest
import tempfile
import shutil
from typing import Generator, AsyncGenerator
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app
from app.db.base import get_db
from app.db.constructor.models import Base as ConstructorBase
from app.db.tutor.models import Base as TutorBase
from app.core.config import settings


# Test database URLs
TEST_CONSTRUCTOR_DB_URL = "mysql+pymysql://root:password@localhost:3306/agentic_tutor_constructor_test"
TEST_TUTOR_DB_URL = "mysql+pymysql://root:password@localhost:3306/agentic_tutor_tutor_test"


@pytest.fixture(scope="session")
def test_engine():
    """Create test database engines."""
    constructor_engine = create_engine(TEST_CONSTRUCTOR_DB_URL, echo=False)
    tutor_engine = create_engine(TEST_TUTOR_DB_URL, echo=False)

    # Create tables
    ConstructorBase.metadata.create_all(constructor_engine)
    TutorBase.metadata.create_all(tutor_engine)

    yield {"constructor": constructor_engine, "tutor": tutor_engine}

    # Cleanup
    ConstructorBase.metadata.drop_all(constructor_engine)
    TutorBase.metadata.drop_all(tutor_engine)
    constructor_engine.dispose()
    tutor_engine.dispose()


@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    """Create a test database session."""
    constructor_engine = test_engine["constructor"]

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=constructor_engine)
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def test_vector_db_path() -> Generator[Path, None, None]:
    """Create a temporary vector database path."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_creator_token(async_client: AsyncClient) -> str:
    """Create a test creator and return auth token."""
    response = await async_client.post(
        "/api/v1/auth/constructor/register",
        json={
            "email": "test_creator@example.com",
            "password": "testpass123",
            "full_name": "Test Creator"
        }
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def test_student_token(async_client: AsyncClient) -> str:
    """Create a test student and return auth token."""
    response = await async_client.post(
        "/api/v1/auth/student/register",
        json={
            "email": "test_student@example.com",
            "password": "testpass123",
            "full_name": "Test Student",
            "age": 20,
            "gender": "other",
            "education_level": "undergraduate"
        }
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def auth_headers_creator(test_creator_token: str) -> dict:
    """Return headers with creator auth token."""
    return {"Authorization": f"Bearer {test_creator_token}"}


@pytest.fixture
def auth_headers_student(test_student_token: str) -> dict:
    """Return headers with student auth token."""
    return {"Authorization": f"Bearer {test_student_token}"}


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self):
        self.messages = []
        self.closed = False

    async def send_json(self, data: dict):
        self.messages.append(data)

    async def send_text(self, text: str):
        self.messages.append(text)

    async def close(self):
        self.closed = True

    def get_messages(self) -> list:
        return self.messages


@pytest.fixture
def mock_websocket() -> MockWebSocket:
    """Create a mock WebSocket."""
    return MockWebSocket()
