"""Node functions for the Ingestion Agent."""

import logging
from datetime import datetime
from typing import Any, Dict, List

from ..state import ConstructorState, UploadedFile
from ..tools.ingestion import (
    ingest_pdf,
    ingest_ppt,
    ingest_docx,
    ingest_video,
    chunk_content_by_semantic,
)

logger = logging.getLogger(__name__)


async def detect_file_types_node(state: ConstructorState) -> Dict[str, Any]:
    """
    Analyze uploaded files and determine their types.

    Groups files by type for batch processing.
    """
    uploaded_files = state.get("uploaded_files", [])

    files_by_type: Dict[str, List[UploadedFile]] = {
        "pdf": [],
        "ppt": [],
        "docx": [],
        "video": [],
        "text": [],
        "other": [],
    }

    for file in uploaded_files:
        if file.get("status") == "completed":
            continue  # Skip already processed files

        file_type = file.get("file_type", "").lower()

        if file_type == "pdf":
            files_by_type["pdf"].append(file)
        elif file_type in ["ppt", "pptx"]:
            files_by_type["ppt"].append(file)
        elif file_type in ["doc", "docx"]:
            files_by_type["docx"].append(file)
        elif file_type == "video":
            files_by_type["video"].append(file)
        elif file_type == "text":
            files_by_type["text"].append(file)
        else:
            files_by_type["other"].append(file)

    return {
        "subagent_results": {
            **state.get("subagent_results", {}),
            "ingestion": {
                "files_by_type": {k: len(v) for k, v in files_by_type.items()},
                "total_pending": sum(len(v) for v in files_by_type.values()),
            },
        },
    }


async def extract_content_node(state: ConstructorState) -> Dict[str, Any]:
    """
    Extract content from all uploaded files.

    Processes each file using the appropriate ingestion tool.
    """
    uploaded_files = state.get("uploaded_files", [])
    course_id = state.get("course_id")

    if not course_id:
        return {
            "errors": ["Cannot process files without a course_id"],
        }

    processed_files = state.get("processed_files", [])
    extracted_contents = []
    errors = []

    for file in uploaded_files:
        if file.get("status") == "completed":
            continue

        file_path = file.get("file_path", "")
        file_type = file.get("file_type", "").lower()

        try:
            # Call appropriate ingestion function
            if file_type == "pdf":
                result = await ingest_pdf.ainvoke({
                    "file_path": file_path,
                    "course_id": course_id,
                })
            elif file_type in ["ppt", "pptx"]:
                result = await ingest_ppt.ainvoke({
                    "file_path": file_path,
                    "course_id": course_id,
                })
            elif file_type in ["doc", "docx"]:
                result = await ingest_docx.ainvoke({
                    "file_path": file_path,
                    "course_id": course_id,
                })
            elif file_type == "video":
                result = await ingest_video.ainvoke({
                    "file_path": file_path,
                    "course_id": course_id,
                    "transcript": file.get("metadata", {}).get("transcript"),
                })
            else:
                result = {"success": False, "error": f"Unsupported file type: {file_type}"}

            if result.get("success"):
                extracted_contents.append({
                    "file_id": file.get("file_id"),
                    "content": result.get("content", ""),
                    "pages_or_slides": result.get("pages_or_slides", 0),
                    "metadata": result.get("metadata", {}),
                })

                # Mark file as processed
                processed_file = {**file, "status": "completed"}
                processed_files.append(processed_file)
            else:
                errors.append(f"Failed to process {file.get('original_filename')}: {result.get('error')}")
                processed_file = {**file, "status": "error", "error_message": result.get("error")}
                processed_files.append(processed_file)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error processing file {file_path}: {error_msg}")
            errors.append(f"Error processing {file.get('original_filename')}: {error_msg}")
            processed_file = {**file, "status": "error", "error_message": error_msg}
            processed_files.append(processed_file)

    return {
        "processed_files": processed_files,
        "extracted_contents": extracted_contents,
        "errors": errors,
        "progress": 0.3,  # 30% complete after extraction
    }


async def chunk_content_node(state: ConstructorState) -> Dict[str, Any]:
    """
    Chunk extracted content into manageable pieces.

    Uses semantic chunking for better context preservation.
    """
    extracted_contents = state.get("extracted_contents", [])
    all_chunks = []

    for extracted in extracted_contents:
        content = extracted.get("content", "")
        if not content:
            continue

        # Use semantic chunking
        result = await chunk_content_by_semantic.ainvoke({
            "content": content,
            "min_chunk_size": 200,
            "max_chunk_size": 1500,
        })

        chunks = result.get("chunks", [])

        # Add source metadata to each chunk
        for chunk in chunks:
            chunk["source_file"] = extracted.get("file_id")
            chunk["source_metadata"] = extracted.get("metadata", {})

        all_chunks.extend(chunks)

    return {
        "content_chunks": all_chunks,
        "progress": 0.5,  # 50% complete after chunking
    }


async def store_chunks_node(state: ConstructorState) -> Dict[str, Any]:
    """
    Store chunks in the vector database.

    Generates embeddings and persists to ChromaDB.
    """
    from ..tools.ingestion import generate_embeddings_for_chunks

    content_chunks = state.get("content_chunks", [])
    course_id = state.get("course_id")

    if not course_id or not content_chunks:
        return {
            "progress": 0.6,
        }

    # Store chunks in vector DB
    result = await generate_embeddings_for_chunks.ainvoke({
        "chunks": content_chunks,
        "course_id": course_id,
    })

    if result.get("success"):
        return {
            "content_chunks": [
                {**chunk, "vector_id": result.get("chunk_ids", [])[i]}
                for i, chunk in enumerate(content_chunks)
                if i < len(result.get("chunk_ids", []))
            ],
            "progress": 0.7,
        }
    else:
        return {
            "errors": [f"Failed to store chunks: {result.get('error')}"],
            "progress": 0.6,
        }


async def report_completion_node(state: ConstructorState) -> Dict[str, Any]:
    """
    Report completion of ingestion processing.

    Summarizes what was processed and any issues.
    """
    processed_files = state.get("processed_files", [])
    content_chunks = state.get("content_chunks", [])
    errors = state.get("errors", [])

    successful = sum(1 for f in processed_files if f.get("status") == "completed")
    failed = sum(1 for f in processed_files if f.get("status") == "error")

    summary = {
        "files_processed": successful,
        "files_failed": failed,
        "total_chunks_created": len(content_chunks),
        "errors": errors,
    }

    # Create message for coordinator
    message = f"Ingestion complete: {successful} files processed, {len(content_chunks)} chunks created."
    if failed > 0:
        message += f" {failed} files failed."

    return {
        "phase": "ingestion_complete",
        "progress": 0.75,
        "subagent_results": {
            **state.get("subagent_results", {}),
            "ingestion": {
                "status": "completed",
                "summary": summary,
            },
        },
        "messages": [{
            "role": "assistant",
            "content": message,
            "timestamp": datetime.utcnow().isoformat(),
        }],
    }
