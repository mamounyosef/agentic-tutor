"""Vector database operations using ChromaDB.

This module provides wrappers for:
- Constructor Vector DB (per course)
- Student Vector DBs (per student, per course)
- Course Vector DBs (read-only for students)
"""

from .embeddings import get_embeddings
from .constructor_store import ConstructorVectorStore
from .student_store import StudentVectorStore

__all__ = [
    "get_embeddings",
    "ConstructorVectorStore",
    "StudentVectorStore",
]
