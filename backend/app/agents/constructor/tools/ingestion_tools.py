"""Content extraction tools for the Constructor agent system.

These tools allow the ingestion sub-agent to extract text from
various file types: PDFs, videos (via transcription), slides, documents.
"""

import json
import os
from typing import Dict, Optional

from langchain_core.tools import tool

from app.core.transcription import transcribe_video


@tool
def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text from a PDF file.

    Use this tool to process uploaded PDF course materials.
    Returns the full text content of the PDF.

    Args:
        file_path: Full path to the PDF file on disk

    Returns:
        JSON string with extracted text and metadata
    """
    try:
        import pypdf
    except ImportError:
        return json.dumps({
            "success": False,
            "text": "",
            "error": "pypdf not installed. Run: pip install pypdf"
        })

    try:
        if not os.path.exists(file_path):
            return json.dumps({
                "success": False,
                "text": "",
                "error": f"File not found: {file_path}"
            })

        reader = pypdf.PdfReader(file_path)
        page_count = len(reader.pages)

        # Extract text from all pages
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

        full_text = "\n\n".join(text_parts)

        return json.dumps({
            "success": True,
            "text": full_text,
            "page_count": page_count,
            "file_path": file_path
        })

    except Exception as e:
        return json.dumps({
            "success": False,
            "text": "",
            "error": f"PDF extraction failed: {str(e)}"
        })


@tool
def extract_text_from_slides(file_path: str) -> str:
    """
    Extract text from PowerPoint slides (.ppt, .pptx).

    Use this tool to process uploaded presentation course materials.
    Returns the text content from all slides.

    Args:
        file_path: Full path to the presentation file on disk

    Returns:
        JSON string with extracted text and metadata
    """
    try:
        from pptx import Presentation
    except ImportError:
        return json.dumps({
            "success": False,
            "text": "",
            "error": "python-pptx not installed. Run: pip install python-pptx"
        })

    try:
        if not os.path.exists(file_path):
            return json.dumps({
                "success": False,
                "text": "",
                "error": f"File not found: {file_path}"
            })

        prs = Presentation(file_path)
        slide_count = len(prs.slides)

        # Extract text from all slides
        text_parts = []
        for slide_num, slide in enumerate(prs.slides, 1):
            slide_text = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text:
                    slide_text.append(shape.text)

            if slide_text:
                text_parts.append(f"--- Slide {slide_num} ---\n" + "\n".join(slide_text))

        full_text = "\n\n".join(text_parts)

        return json.dumps({
            "success": True,
            "text": full_text,
            "slide_count": slide_count,
            "file_path": file_path
        })

    except Exception as e:
        return json.dumps({
            "success": False,
            "text": "",
            "error": f"Slide extraction failed: {str(e)}"
        })


@tool
async def transcribe_video_file(file_path: str, language: Optional[str] = None) -> str:
    """
    Transcribe audio from a video file.

    Use this tool to extract spoken content from video course materials.
    Returns the full transcript text.

    Args:
        file_path: Full path to the video file on disk
        language: Optional language code (e.g., "en", "es", "auto")

    Returns:
        JSON string with transcription result and metadata
    """
    try:
        if not os.path.exists(file_path):
            return json.dumps({
                "success": False,
                "text": "",
                "error": f"File not found: {file_path}"
            })

        result = await transcribe_video(file_path, language)

        if result.get("error"):
            return json.dumps({
                "success": False,
                "text": result.get("text", ""),
                "error": result["error"]
            })

        return json.dumps({
            "success": True,
            "text": result.get("text", ""),
            "duration": result.get("duration", 0),
            "language": result.get("language"),
            "file_path": file_path
        })

    except Exception as e:
        return json.dumps({
            "success": False,
            "text": "",
            "error": f"Video transcription failed: {str(e)}"
        })


@tool
def extract_text_from_document(file_path: str) -> str:
    """
    Extract text from document files (.txt, .md, .docx).

    Use this tool to process text-based course materials.
    Returns the full text content.

    Args:
        file_path: Full path to the document file on disk

    Returns:
        JSON string with extracted text and metadata
    """
    try:
        if not os.path.exists(file_path):
            return json.dumps({
                "success": False,
                "text": "",
                "error": f"File not found: {file_path}"
            })

        file_ext = os.path.splitext(file_path)[1].lower()

        # Handle plain text files
        if file_ext in ['.txt', '.md']:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()

            return json.dumps({
                "success": True,
                "text": text,
                "file_type": file_ext,
                "file_path": file_path
            })

        # Handle Word documents
        elif file_ext == '.docx':
            try:
                from docx import Document
            except ImportError:
                return json.dumps({
                    "success": False,
                    "text": "",
                    "error": "python-docx not installed. Run: pip install python-docx"
                })

            doc = Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs if para.text])

            return json.dumps({
                "success": True,
                "text": text,
                "file_type": "docx",
                "file_path": file_path
            })

        else:
            return json.dumps({
                "success": False,
                "text": "",
                "error": f"Unsupported document type: {file_ext}"
            })

    except Exception as e:
        return json.dumps({
            "success": False,
            "text": "",
            "error": f"Document extraction failed: {str(e)}"
        })
