"""Structure analysis tools for course organization.

Tools for detecting topics, organizing content into units, and identifying
prerequisite relationships between topics.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.agents.base.llm import get_llm

logger = logging.getLogger(__name__)


class DetectedTopic(BaseModel):
    """A detected topic from content analysis."""

    title: str
    description: str
    key_concepts: List[str]
    source_chunk_ids: List[str]


class TopicRelationship(BaseModel):
    """A relationship between topics."""

    topic_id: str
    prerequisite_topic_ids: List[str]


class UnitOrganization(BaseModel):
    """Organized unit structure."""

    unit_title: str
    unit_description: str
    topic_titles: List[str]


# =============================================================================
# Topic Detection
# =============================================================================

TOPIC_DETECTION_PROMPT = """Analyze the following content chunks from an educational course and identify distinct learning topics.

For each topic you identify, provide:
1. A clear, concise title
2. A brief description of what the topic covers
3. Key concepts that students should learn
4. The chunk IDs that relate to this topic

Content chunks:
{chunks_json}

Return a JSON array of topics with this structure:
[
  {{
    "title": "Topic Title",
    "description": "Brief description",
    "key_concepts": ["concept1", "concept2"],
    "source_chunk_ids": ["chunk_0", "chunk_1"]
  }}
]

Identify topics that represent distinct learning objectives. Aim for 5-15 topics depending on content complexity.
"""


@tool
async def detect_topics_from_chunks(
    chunks: List[Dict[str, Any]],
    course_title: str = "",
) -> Dict[str, Any]:
    """
    Use LLM to detect topics from content chunks.

    Args:
        chunks: List of content chunks with 'chunk_id', 'text', and optional metadata
        course_title: Optional course title for context

    Returns:
        Dictionary with detected topics
    """
    if not chunks:
        return {"topics": [], "success": False, "error": "No chunks provided"}

    try:
        # Prepare chunks for LLM analysis
        chunks_for_analysis = [
            {
                "chunk_id": chunk.get("chunk_id", f"chunk_{i}"),
                "text": chunk.get("text", "")[:500],  # Truncate for token limits
            }
            for i, chunk in enumerate(chunks)
        ]

        llm = get_llm(temperature=0.3)

        prompt = TOPIC_DETECTION_PROMPT.format(
            chunks_json=json.dumps(chunks_for_analysis, indent=2)
        )

        if course_title:
            prompt = f"Course Title: {course_title}\n\n{prompt}"

        response = await llm.ainvoke(prompt)

        # Parse the response
        content = response.content

        # Try to extract JSON from the response
        try:
            # Handle markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            topics = json.loads(content.strip())
        except json.JSONDecodeError:
            # If parsing fails, try to extract topics with regex
            logger.warning("Failed to parse JSON response, attempting fallback")
            topics = []

        return {
            "success": True,
            "topics": topics,
            "total_topics": len(topics),
        }

    except Exception as e:
        logger.error(f"Error detecting topics: {e}")
        return {
            "success": False,
            "topics": [],
            "error": str(e),
        }


# =============================================================================
# Unit Organization
# =============================================================================

UNIT_ORGANIZATION_PROMPT = """Organize the following topics into logical course units.

Topics:
{topics_json}

Create 3-6 units that group related topics together. Each unit should:
1. Have a clear, descriptive title
2. Cover a coherent theme or area
3. Progress logically from fundamentals to advanced concepts

Return a JSON array of units:
[
  {{
    "unit_title": "Unit Title",
    "unit_description": "What this unit covers",
    "topic_titles": ["Topic 1", "Topic 2"]
  }}
]

All topics must be assigned to exactly one unit.
"""


@tool
async def organize_chunks_into_units(
    topics: List[Dict[str, Any]],
    course_title: str = "",
) -> Dict[str, Any]:
    """
    Organize detected topics into logical course units.

    Args:
        topics: List of detected topics
        course_title: Optional course title for context

    Returns:
        Dictionary with organized units
    """
    if not topics:
        return {"units": [], "success": False, "error": "No topics provided"}

    try:
        # Prepare topics for LLM
        topics_for_org = [
            {
                "title": t.get("title", ""),
                "description": t.get("description", ""),
                "key_concepts": t.get("key_concepts", []),
            }
            for t in topics
        ]

        llm = get_llm(temperature=0.3)

        prompt = UNIT_ORGANIZATION_PROMPT.format(
            topics_json=json.dumps(topics_for_org, indent=2)
        )

        if course_title:
            prompt = f"Course Title: {course_title}\n\n{prompt}"

        response = await llm.ainvoke(prompt)
        content = response.content

        # Parse JSON
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            units = json.loads(content.strip())
        except json.JSONDecodeError:
            logger.warning("Failed to parse unit organization response")
            units = []

        # Map topics to units
        organized_topics = []
        for unit_idx, unit in enumerate(units):
            for topic_title in unit.get("topic_titles", []):
                # Find the original topic
                for original_topic in topics:
                    if original_topic.get("title") == topic_title:
                        organized_topics.append({
                            **original_topic,
                            "unit_index": unit_idx,
                            "unit_title": unit.get("unit_title", ""),
                        })
                        break

        return {
            "success": True,
            "units": units,
            "total_units": len(units),
            "organized_topics": organized_topics,
        }

    except Exception as e:
        logger.error(f"Error organizing units: {e}")
        return {
            "success": False,
            "units": [],
            "error": str(e),
        }


# =============================================================================
# Prerequisite Identification
# =============================================================================

PREREQUISITE_PROMPT = """Analyze the following topics and identify prerequisite relationships.

Topics:
{topics_json}

For each topic, determine which other topics must be understood first (prerequisites).
Consider:
1. Foundational concepts that must come before advanced ones
2. Topics that build upon knowledge from other topics
3. Logical learning progression

Return a JSON array:
[
  {{
    "topic_title": "Topic Title",
    "prerequisite_titles": ["Prerequisite Topic 1", "Prerequisite Topic 2"]
  }}
]

Only include direct prerequisites, not transitive ones. A topic with no prerequisites should have an empty array.
"""


@tool
async def identify_prerequisite_relationships(
    topics: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Identify prerequisite relationships between topics.

    Args:
        topics: List of topics with titles and descriptions

    Returns:
        Dictionary with prerequisite mappings
    """
    if not topics:
        return {"relationships": [], "success": False, "error": "No topics provided"}

    try:
        topics_for_analysis = [
            {
                "title": t.get("title", ""),
                "description": t.get("description", ""),
                "key_concepts": t.get("key_concepts", []),
            }
            for t in topics
        ]

        llm = get_llm(temperature=0.3)

        prompt = PREREQUISITE_PROMPT.format(
            topics_json=json.dumps(topics_for_analysis, indent=2)
        )

        response = await llm.ainvoke(prompt)
        content = response.content

        # Parse JSON
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            relationships = json.loads(content.strip())
        except json.JSONDecodeError:
            logger.warning("Failed to parse prerequisite response")
            relationships = []

        # Build prerequisite map
        prereq_map = {}
        for rel in relationships:
            topic_title = rel.get("topic_title", "")
            prereq_titles = rel.get("prerequisite_titles", [])
            prereq_map[topic_title] = prereq_titles

        return {
            "success": True,
            "relationships": relationships,
            "prerequisite_map": prereq_map,
        }

    except Exception as e:
        logger.error(f"Error identifying prerequisites: {e}")
        return {
            "success": False,
            "relationships": [],
            "error": str(e),
        }


# =============================================================================
# Topic Summary Generation
# =============================================================================

SUMMARY_PROMPT = """Create a concise summary of the following topic for a course.

Topic: {topic_title}
Description: {topic_description}
Key Concepts: {key_concepts}

Content:
{content}

Write a 2-3 sentence summary that captures the essential learning objectives for this topic.
"""


@tool
async def generate_topic_summary(
    topic_title: str,
    topic_description: str,
    key_concepts: List[str],
    content_chunks: List[str],
) -> Dict[str, Any]:
    """
    Generate a concise summary for a topic.

    Args:
        topic_title: Title of the topic
        topic_description: Description of the topic
        key_concepts: List of key concepts
        content_chunks: Related content chunks

    Returns:
        Dictionary with generated summary
    """
    try:
        llm = get_llm(temperature=0.5)

        # Combine content chunks (limit to avoid token limits)
        combined_content = "\n\n".join(content_chunks[:3])[:2000]

        prompt = SUMMARY_PROMPT.format(
            topic_title=topic_title,
            topic_description=topic_description,
            key_concepts=", ".join(key_concepts),
            content=combined_content,
        )

        response = await llm.ainvoke(prompt)

        return {
            "success": True,
            "summary": response.content.strip(),
        }

    except Exception as e:
        logger.error(f"Error generating topic summary: {e}")
        return {
            "success": False,
            "summary": "",
            "error": str(e),
        }
