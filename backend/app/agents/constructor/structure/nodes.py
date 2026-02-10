"""Node functions for the Structure Analysis Agent.

Each node represents a step in the structure analysis workflow:
1. analyze_content - Initial content analysis
2. detect_topics - Extract learning topics from chunks
3. group_into_units - Organize topics into logical units
4. identify_prerequisites - Find prerequisite relationships
5. build_hierarchy - Build the complete structure hierarchy
6. validate_structure - Check for circular deps and other issues
7. suggest_organization - Present structure to creator
8. finalize_structure - Create final structure and save
"""

import json
import logging
from typing import Any, Dict, List

from ..state import TopicInfo, UnitInfo
from ..tools.structure import (
    detect_topics_from_chunks,
    identify_prerequisite_relationships,
    organize_chunks_into_units,
)
from .prompts import (
    COMPLETION_MESSAGE,
    PREREQUISITE_IDENTIFICATION_NODE_PROMPT,
    SUGGEST_ORGANIZATION_PROMPT,
    TOPIC_DETECTION_NODE_PROMPT,
    UNIT_ORGANIZATION_NODE_PROMPT,
)
from .state import (
    DetectedTopic,
    DetectedUnit,
    StructureState,
    TopicRelationship,
)

logger = logging.getLogger(__name__)


async def analyze_content_node(state: StructureState) -> Dict[str, Any]:
    """
    Analyze the ingested content chunks.

    Validates input and prepares for topic detection.
    """
    content_chunks = state.get("content_chunks", [])
    course_title = state.get("course_title", "")

    if not content_chunks:
        return {
            "errors": ["No content chunks to analyze"],
            "phase": "analyze_content",
        }

    # Create a summary of chunks for logging
    chunks_summary = f"Total chunks: {len(content_chunks)}"
    logger.info(f"Analyzing content for course: {course_title} - {chunks_summary}")

    return {
        "phase": "detect_topics",
        "errors": [],
    }


async def detect_topics_node(state: StructureState) -> Dict[str, Any]:
    """
    Detect distinct learning topics from content chunks.

    Uses the LLM to identify topics based on content analysis.
    """
    content_chunks = state.get("content_chunks", [])
    course_title = state.get("course_title", "")

    # Use the structure tool to detect topics
    result = await detect_topics_from_chunks.ainvoke({
        "chunks": content_chunks,
        "course_title": course_title,
    })

    if not result.get("success"):
        return {
            "errors": [result.get("error", "Failed to detect topics")],
            "phase": "detect_topics",
        }

    topics_data = result.get("topics", [])
    detected_topics: List[DetectedTopic] = []

    for i, topic_data in enumerate(topics_data):
        detected_topics.append(DetectedTopic(
            title=topic_data.get("title", f"Topic {i+1}"),
            description=topic_data.get("description", ""),
            key_concepts=topic_data.get("key_concepts", []),
            source_chunk_ids=topic_data.get("source_chunk_ids", []),
            summary=None,
            unit_index=None,
            order_index=i,
        ))

    # Calculate confidence scores (simplified - could be enhanced)
    confidence_scores = {
        topic["title"]: topic.get("confidence", 0.8)
        for topic in topics_data
    }

    return {
        "detected_topics": detected_topics,
        "total_topics": len(detected_topics),
        "confidence_scores": confidence_scores,
        "phase": "organize_units",
    }


async def group_into_units_node(state: StructureState) -> Dict[str, Any]:
    """
    Group detected topics into logical course units.

    Uses the LLM to organize topics into coherent units.
    """
    detected_topics = state.get("detected_topics", [])
    course_title = state.get("course_title", "")

    if not detected_topics:
        return {
            "errors": ["No topics to organize into units"],
            "phase": "organize_units",
        }

    # Prepare topics for the tool
    topics_for_tool = [
        {
            "title": t.get("title", ""),
            "description": t.get("description", ""),
            "key_concepts": t.get("key_concepts", []),
        }
        for t in detected_topics
    ]

    # Use the structure tool to organize into units
    result = await organize_chunks_into_units.ainvoke({
        "topics": topics_for_tool,
        "course_title": course_title,
    })

    if not result.get("success"):
        return {
            "errors": [result.get("error", "Failed to organize units")],
            "phase": "organize_units",
        }

    units_data = result.get("units", [])
    detected_units: List[DetectedUnit] = []

    for i, unit_data in enumerate(units_data):
        detected_units.append(DetectedUnit(
            title=unit_data.get("unit_title", f"Unit {i+1}"),
            description=unit_data.get("unit_description", ""),
            order_index=i,
            topic_titles=unit_data.get("topic_titles", []),
        ))

    # Organize topics by unit
    organized_topics: List[DetectedTopic] = []
    topics_by_unit: Dict[str, List[DetectedTopic]] = {}

    for unit in detected_units:
        unit_title = unit["title"]
        topics_by_unit[unit_title] = []

        for topic_title in unit.get("topic_titles", []):
            for topic in detected_topics:
                if topic.get("title") == topic_title:
                    # Update topic with unit info
                    updated_topic = DetectedTopic(
                        **topic,
                        unit_index=unit.get("order_index"),
                    )
                    organized_topics.append(updated_topic)
                    topics_by_unit[unit_title].append(updated_topic)
                    break

    return {
        "detected_units": detected_units,
        "total_units": len(detected_units),
        "topics_by_unit": topics_by_unit,
        "detected_topics": organized_topics,
        "phase": "identify_prerequisites",
    }


async def identify_prerequisites_node(state: StructureState) -> Dict[str, Any]:
    """
    Identify prerequisite relationships between topics.

    Uses the LLM to determine which topics require knowledge from others.
    """
    detected_topics = state.get("detected_topics", [])

    if not detected_topics:
        return {
            "errors": ["No topics to analyze for prerequisites"],
            "phase": "identify_prerequisites",
        }

    # Prepare topics for the tool
    topics_for_tool = [
        {
            "title": t.get("title", ""),
            "description": t.get("description", ""),
            "key_concepts": t.get("key_concepts", []),
        }
        for t in detected_topics
    ]

    # Use the structure tool to identify prerequisites
    result = await identify_prerequisite_relationships.ainvoke({
        "topics": topics_for_tool,
    })

    if not result.get("success"):
        return {
            "errors": [result.get("error", "Failed to identify prerequisites")],
            "phase": "identify_prerequisites",
        }

    relationships_data = result.get("relationships", [])
    topic_relationships: List[TopicRelationship] = []
    prerequisite_map: Dict[str, List[str]] = {}

    for rel in relationships_data:
        topic_title = rel.get("topic_title", "")
        prereq_titles = rel.get("prerequisite_titles", [])

        topic_relationships.append(TopicRelationship(
            topic_title=topic_title,
            prerequisite_titles=prereq_titles,
            confidence=rel.get("confidence", 0.8),
        ))

        prerequisite_map[topic_title] = prereq_titles

    return {
        "topic_relationships": topic_relationships,
        "prerequisite_map": prerequisite_map,
        "phase": "build_hierarchy",
    }


async def build_hierarchy_node(state: StructureState) -> Dict[str, Any]:
    """
    Build the complete course structure hierarchy.

    Combines units, topics, and relationships into a final structure.
    """
    detected_units = state.get("detected_units", [])
    detected_topics = state.get("detected_topics", [])
    prerequisite_map = state.get("prerequisite_map", {})
    topics_by_unit = state.get("topics_by_unit", {})

    # Build the hierarchy structure
    structure_hierarchy: Dict[str, Any] = {
        "course_id": state.get("course_id"),
        "units": [],
        "total_units": len(detected_units),
        "total_topics": len(detected_topics),
    }

    for unit in detected_units:
        unit_title = unit.get("title", "")
        unit_topics = topics_by_unit.get(unit_title, [])

        # Build topic list with prerequisites
        topics_with_prereqs = []
        for topic in unit_topics:
            topic_title = topic.get("title", "")
            topics_with_prereqs.append({
                "title": topic_title,
                "description": topic.get("description", ""),
                "key_concepts": topic.get("key_concepts", []),
                "prerequisites": prerequisite_map.get(topic_title, []),
                "order_index": topic.get("order_index", 0),
            })

        structure_hierarchy["units"].append({
            "title": unit_title,
            "description": unit.get("description", ""),
            "order_index": unit.get("order_index", 0),
            "topics": topics_with_prereqs,
        })

    return {
        "structure_hierarchy": structure_hierarchy,
        "phase": "validate_structure",
    }


async def validate_structure_node(state: StructureState) -> Dict[str, Any]:
    """
    Validate the course structure for issues.

    Checks for:
    - Circular prerequisite chains
    - Orphaned topics
    - Unreachable topics
    """
    prerequisite_map = state.get("prerequisite_map", {})
    detected_topics = state.get("detected_topics", [])
    warnings = []
    errors = []

    # Get all topic titles
    all_topics = {t.get("title", "") for t in detected_topics}

    # Check for circular references using DFS
    def has_cycle(topic: str, visited: set, rec_stack: set, path: list) -> bool:
        visited.add(topic)
        rec_stack.add(topic)
        path.append(topic)

        prereqs = prerequisite_map.get(topic, [])
        for prereq in prereqs:
            if prereq not in all_topics:
                warnings.append(f"Topic '{topic}' references unknown prerequisite '{prereq}'")
                continue

            if prereq not in visited:
                if has_cycle(prereq, visited, rec_stack, path):
                    return True
            elif prereq in rec_stack:
                cycle = " -> ".join(path + [prereq])
                errors.append(f"Circular prerequisite detected: {cycle}")
                return True

        rec_stack.remove(topic)
        path.pop()
        return False

    visited = set()
    for topic in all_topics:
        if topic not in visited:
            has_cycle(topic, visited, set(), [])

    # Check for orphaned topics (no incoming or outgoing dependencies)
    topics_with_prereqs = set(prerequisite_map.keys())
    all_mentioned = set()
    for prereqs in prerequisite_map.values():
        all_mentioned.update(prereqs)

    orphans = all_topics - topics_with_prereqs - all_mentioned
    if orphans:
        warnings.append(f"Orphaned topics (no dependencies): {list(orphans)}")

    # Calculate quality score
    quality_score = 1.0
    if errors:
        quality_score -= 0.5 * len(errors)
    if warnings:
        quality_score -= 0.1 * len(warnings)
    quality_score = max(0.0, quality_score)

    return {
        "errors": errors,
        "warnings": warnings,
        "phase": "suggest_organization",
    }


async def suggest_organization_node(state: StructureState) -> Dict[str, Any]:
    """
    Present the proposed structure to the creator for review.

    Generates a human-readable summary of the structure.
    """
    detected_units = state.get("detected_units", [])
    detected_topics = state.get("detected_topics", [])
    topic_relationships = state.get("topic_relationships", [])
    errors = state.get("errors", [])

    # Generate units summary
    units_summary = ""
    for unit in detected_units:
        units_summary += f"\n### {unit.get('title')}\n"
        units_summary += f"{unit.get('description', '')}\n"
        units_summary += f"Topics: {', '.join(unit.get('topic_titles', []))}\n"

    # Generate topics summary
    topics_summary = ""
    for topic in detected_topics:
        topics_summary += f"\n- **{topic.get('title')}**: {topic.get('description', '')}\n"

    # Generate prerequisites summary
    prereqs_summary = ""
    for rel in topic_relationships:
        if rel.get("prerequisite_titles"):
            prereqs_summary += f"\n- {rel.get('title')} requires: {', '.join(rel.get('prerequisite_titles', []))}\n"

    # Generate the message
    message = SUGGEST_ORGANIZATION_PROMPT.format(
        total_units=len(detected_units),
        units_summary=units_summary,
        total_topics=len(detected_topics),
        topics_summary=topics_summary,
        prerequisites_summary=prereqs_summary or "No prerequisite relationships identified.",
    )

    return {
        "awaiting_approval": True,
        "phase": "finalize",
    }


async def finalize_structure_node(state: StructureState) -> Dict[str, Any]:
    """
    Finalize the structure and prepare for storage.

    Converts the structure to the format expected by the database.
    """
    structure_hierarchy = state.get("structure_hierarchy", {})
    detected_units = state.get("detected_units", [])
    detected_topics = state.get("detected_topics", [])

    # Convert to UnitInfo and TopicInfo formats for storage
    units_for_db: List[UnitInfo] = []
    topics_for_db: List[TopicInfo] = []

    for unit in detected_units:
        unit_title = unit.get("title", "")

        # Find topics for this unit
        unit_topics = [
            t for t in detected_topics
            if t.get("unit_index") == unit.get("order_index")
        ]

        # Create TopicInfo objects
        topic_infos: List[TopicInfo] = []
        for topic in unit_topics:
            topic_infos.append(TopicInfo(
                id=None,  # Will be assigned by database
                title=topic.get("title", ""),
                description=topic.get("description", ""),
                content_summary=topic.get("summary", ""),
                prerequisites=[],  # Will be resolved after DB insert
                unit_id=None,
                order_index=topic.get("order_index", 0),
            ))

        # Create UnitInfo
        units_for_db.append(UnitInfo(
            id=None,
            title=unit_title,
            description=unit.get("description", ""),
            order_index=unit.get("order_index", 0),
            topics=topic_infos,
        ))

        topics_for_db.extend(topic_infos)

    # Generate completion message
    quality_score = 1.0 - (0.1 * len(state.get("warnings", []))) - (0.5 * len(state.get("errors", [])))
    quality_score = max(0.0, quality_score)

    completion_msg = COMPLETION_MESSAGE.format(
        total_units=len(detected_units),
        total_topics=len(detected_topics),
        total_relationships=len(state.get("topic_relationships", [])),
        quality_score=f"{quality_score:.2f}",
    )

    return {
        "analysis_complete": True,
        "structure_for_db": {
            "units": units_for_db,
            "topics": topics_for_db,
        },
        "phase": "complete",
    }
