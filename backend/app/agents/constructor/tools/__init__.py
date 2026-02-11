"""Constructor workflow tools.

This module provides LangChain tools for the Constructor Agent:
- File ingestion (PDF, PPT, video, DOCX)
- Content chunking
- Structure analysis (topics, units, prerequisites)
- Quiz generation
- Storage (Vector DB + MySQL)
"""

# Import from local tool modules to avoid circular imports
from .ingestion import (
    ingest_pdf,
    ingest_ppt,
    ingest_video,
    ingest_docx,
    chunk_content_by_semantic,
    chunk_content_by_size,
    generate_embeddings_for_chunks
)

from .structure import (
    detect_topics_from_chunks,
    organize_chunks_into_units,
    identify_prerequisite_relationships,
    generate_topic_summary
)

from .quiz import (
    generate_quiz_question,
    generate_multiple_choice,
    generate_true_false,
    generate_short_answer,
    create_quiz_rubric
)

from .storage import (
    save_material_reference,
    store_chunks_in_vector_db,
    create_course_record,
    create_unit_record,
    create_topic_record,
    save_quiz_question
)

__all__ = [
    # Ingestion tools
    "ingest_pdf",
    "ingest_ppt",
    "ingest_video",
    "ingest_docx",
    "chunk_content_by_semantic",
    "chunk_content_by_size",
    "generate_embeddings_for_chunks",

    # Structure tools
    "detect_topics_from_chunks",
    "organize_chunks_into_units",
    "identify_prerequisite_relationships",
    "generate_topic_summary",

    # Quiz tools
    "generate_quiz_question",
    "generate_multiple_choice",
    "generate_true_false",
    "generate_short_answer",
    "create_quiz_rubric",

    # Storage tools
    "create_course_record",
    "create_unit_record",
    "create_topic_record",
    "save_quiz_question",
    "save_material_reference",
    "store_chunks_in_vector_db",
]
