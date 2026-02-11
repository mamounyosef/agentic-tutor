"""
Test suite for verifying project dependencies and requirements.

This module tests that all required dependencies are properly installed
and accessible for the Agentic Tutor platform.
"""

import sys
import importlib
import pytest


class TestDependencies:
    """Test that all required dependencies are installed."""

    # Core Python dependencies
    def test_python_version(self):
        """Test Python version is 3.11+."""
        major, minor = sys.version_info[:2]
        assert major == 3 and minor >= 11, f"Python 3.11+ required, got {major}.{minor}"

    # FastAPI and web framework
    def test_fastapi_installed(self):
        """Test FastAPI is installed."""
        import fastapi
        assert fastapi.__version__ is not None

    def test_uvicorn_installed(self):
        """Test uvicorn is installed."""
        import uvicorn
        assert uvicorn.__version__ is not None

    def test_websockets_installed(self):
        """Test websockets library is installed."""
        import websockets
        assert websockets.__version__ is not None

    # SQLAlchemy and database
    def test_sqlalchemy_installed(self):
        """Test SQLAlchemy is installed."""
        import sqlalchemy
        assert sqlalchemy.__version__ is not None

    def test_pymysql_installed(self):
        """Test pymysql is installed."""
        import pymysql
        assert pymysql.__version__ is not None

    # LangChain and LangGraph
    def test_langchain_installed(self):
        """Test LangChain is installed."""
        from langchain_core import messages
        assert messages is not None

    def test_langgraph_installed(self):
        """Test LangGraph is installed."""
        from langgraph import checkpoint
        assert checkpoint is not None

    # Vector store
    def test_chromadb_installed(self):
        """Test ChromaDB is installed."""
        import chromadb
        assert chromadb.__version__ is not None

    # Security
    def test_python_jose_installed(self):
        """Test python-jose for JWT is installed."""
        from jose import jwt
        assert jwt is not None

    def test_passlib_installed(self):
        """Test passlib for password hashing is installed."""
        import passlib
        assert passlib.__version__ is not None

    def test_bcrypt_installed(self):
        """Test bcrypt is installed."""
        import bcrypt
        assert bcrypt.__version__ is not None

    # File processing
    def test_pypdf_installed(self):
        """Test PyPDF2 is installed."""
        import pypdf
        assert pypdf.__version__ is not None

    def test_pptx_installed(self):
        """Test python-pptx is installed."""
        import pptx
        assert pptx is not None

    # Utilities
    def test_pydantic_installed(self):
        """Test Pydantic is installed."""
        import pydantic
        assert pydantic.__version__ is not None

    def test_python_dotenv_installed(self):
        """Test python-dotenv is installed."""
        import dotenv
        assert dotenv is not None

    def test_httpx_installed(self):
        """Test httpx is installed."""
        import httpx
        assert httpx.__version__ is not None

    def test_pyyaml_installed(self):
        """Test PyYAML is installed."""
        import yaml
        assert yaml is not None


class TestProjectStructure:
    """Test that required project directories and files exist."""

    def test_backend_structure(self):
        """Test backend directory structure."""
        from pathlib import Path

        backend_path = Path(__file__).parent.parent
        required_dirs = [
            backend_path / "app" / "agents",
            backend_path / "app" / "api",
            backend_path / "app" / "core",
            backend_path / "app" / "db",
            backend_path / "app" / "vector",
        ]

        for dir_path in required_dirs:
            assert dir_path.exists(), f"Required directory not found: {dir_path}"

    def test_schemas_exist(self):
        """Test database schema files exist."""
        from pathlib import Path

        backend_path = Path(__file__).parent.parent
        constructor_schema = backend_path / "db" / "constructor" / "schema.sql"
        tutor_schema = backend_path / "db" / "tutor" / "schema.sql"

        assert constructor_schema.exists(), "Constructor schema not found"
        assert tutor_schema.exists(), "Tutor schema not found"


class TestConfiguration:
    """Test application configuration."""

    def test_config_module_exists(self):
        """Test config module can be imported."""
        from app.core import config
        assert config is not None

    def test_config_has_required_settings(self):
        """Test config has required settings."""
        from app.core.config import settings

        required_attrs = [
            "CONSTRUCTOR_DB_URL",
            "TUTOR_DB_URL",
            "SECRET_KEY",
            "LLM_BASE_URL",
            "LLM_MODEL",
        ]

        for attr in required_attrs:
            assert hasattr(settings, attr), f"Config missing: {attr}"
