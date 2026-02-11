"""Schema compatibility helpers for constructor DB.

This module applies lightweight, idempotent compatibility fixes on startup
for local/dev databases that were created with older SQL schema files.
"""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import text

from app.db.base import get_constructor_engine

logger = logging.getLogger(__name__)


async def _get_column_names(conn, table_name: str) -> set[str]:
    """Return lowercase column names for a table in the current database."""
    query = text(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = :table_name
        """
    )
    result = await conn.execute(query, {"table_name": table_name})
    return {str(row[0]).lower() for row in result.fetchall()}


async def _add_missing_columns(conn, table_name: str, column_defs: dict[str, str]) -> None:
    """Add missing columns to table based on provided DDL fragments."""
    existing = await _get_column_names(conn, table_name)
    for column, ddl in column_defs.items():
        if column.lower() in existing:
            continue
        logger.info("Applying compat migration: add %s.%s", table_name, column)
        await conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column} {ddl}")


async def _try_exec_many(conn, statements: Iterable[str]) -> None:
    """Run SQL statements, logging and continuing on non-critical failures."""
    for sql in statements:
        try:
            await conn.exec_driver_sql(sql)
        except Exception as exc:  # pragma: no cover - defensive for mixed local schemas
            logger.warning("Compat SQL skipped/failed: %s (%s)", sql, exc)


async def _get_index_names(conn, table_name: str) -> set[str]:
    """Return lowercase index names for a table in the current database."""
    query = text(
        """
        SELECT INDEX_NAME
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = :table_name
        """
    )
    result = await conn.execute(query, {"table_name": table_name})
    return {str(row[0]).lower() for row in result.fetchall()}


async def ensure_constructor_schema_compatibility() -> None:
    """Ensure constructor DB has columns required by current ORM models."""
    engine = get_constructor_engine()
    async with engine.begin() as conn:
        # courses table
        await _add_missing_columns(
            conn,
            "courses",
            {
                "course_metadata": "JSON NULL",
            },
        )

        # materials table
        await _add_missing_columns(
            conn,
            "materials",
            {
                "course_id": "INT NULL",
                "course_metadata": "JSON NULL",
                "processing_status": "ENUM('pending','processing','completed','error') DEFAULT 'pending'",
                "chunks_count": "INT DEFAULT 0",
            },
        )

        # quiz_questions table
        await _add_missing_columns(
            conn,
            "quiz_questions",
            {
                "course_id": "INT NULL",
                "course_metadata": "JSON NULL",
            },
        )

        # constructor_sessions table
        await _add_missing_columns(
            conn,
            "constructor_sessions",
            {
                "phase": "VARCHAR(50) DEFAULT 'welcome'",
                "files_uploaded": "INT DEFAULT 0",
                "files_processed": "INT DEFAULT 0",
                "topics_created": "INT DEFAULT 0",
                "questions_created": "INT DEFAULT 0",
            },
        )

        courses_cols = await _get_column_names(conn, "courses")
        materials_cols = await _get_column_names(conn, "materials")
        quiz_cols = await _get_column_names(conn, "quiz_questions")

        backfill_statements: list[str] = []

        if "metadata" in courses_cols and "course_metadata" in courses_cols:
            backfill_statements.append(
                "UPDATE courses SET course_metadata = metadata "
                "WHERE course_metadata IS NULL AND metadata IS NOT NULL"
            )

        if "metadata" in materials_cols and "course_metadata" in materials_cols:
            backfill_statements.append(
                "UPDATE materials SET course_metadata = metadata "
                "WHERE course_metadata IS NULL AND metadata IS NOT NULL"
            )

        if "metadata" in quiz_cols and "course_metadata" in quiz_cols:
            backfill_statements.append(
                "UPDATE quiz_questions SET course_metadata = metadata "
                "WHERE course_metadata IS NULL AND metadata IS NOT NULL"
            )

        # Derive missing course_id from topic -> unit -> course relationship.
        if "course_id" in materials_cols:
            backfill_statements.append(
                "UPDATE materials m "
                "JOIN topics t ON m.topic_id = t.id "
                "JOIN units u ON t.unit_id = u.id "
                "SET m.course_id = u.course_id "
                "WHERE m.course_id IS NULL"
            )

        if "course_id" in quiz_cols:
            backfill_statements.append(
                "UPDATE quiz_questions q "
                "JOIN topics t ON q.topic_id = t.id "
                "JOIN units u ON t.unit_id = u.id "
                "SET q.course_id = u.course_id "
                "WHERE q.course_id IS NULL"
            )

        await _try_exec_many(conn, backfill_statements)

        # Optional indexes for performance/compatibility.
        material_indexes = await _get_index_names(conn, "materials")
        if "idx_materials_course_id" not in material_indexes:
            await conn.exec_driver_sql("CREATE INDEX idx_materials_course_id ON materials(course_id)")

        quiz_indexes = await _get_index_names(conn, "quiz_questions")
        if "idx_quiz_questions_course_id" not in quiz_indexes:
            await conn.exec_driver_sql("CREATE INDEX idx_quiz_questions_course_id ON quiz_questions(course_id)")
