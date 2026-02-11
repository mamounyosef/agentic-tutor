"""State definition for the Structure Analysis Agent.

The Structure Analysis Agent analyzes ingested content to detect topics,
organize them into units, and identify prerequisite relationships.
"""

from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict


class DetectedTopic(TypedDict):
    """A topic detected from content analysis."""

    title: str
    description: str
    key_concepts: List[str]
    source_chunk_ids: List[str]
    summary: Optional[str]
    unit_index: Optional[int]
    order_index: int


class DetectedUnit(TypedDict):
    """A unit that groups related topics."""

    title: str
    description: str
    order_index: int
    topic_titles: List[str]


class TopicRelationship(TypedDict):
    """A prerequisite relationship between topics."""

    topic_title: str
    prerequisite_titles: List[str]
    confidence: float  # 0.0 to 1.0


class StructureState(TypedDict):
    """
    State for the Structure Analysis Agent.

    This agent processes ingested content chunks and organizes them
    into a coherent course structure with units and topics.
    """

    # Input
    course_id: str
    course_title: str
    content_chunks: List[Dict[str, Any]]

    # Analysis phase
    phase: str  # "analyze_content" | "detect_topics" | "organize_units" | "identify_prerequisites" | "build_hierarchy" | "finalize"

    # Detected topics
    detected_topics: List[DetectedTopic]
    total_topics: int

    # Organized units
    detected_units: List[DetectedUnit]
    total_units: int

    # Prerequisite relationships
    topic_relationships: List[TopicRelationship]
    prerequisite_map: Dict[str, List[str]]  # topic_title -> prerequisite_titles

    # Final structure hierarchy
    structure_hierarchy: Dict[str, Any]
    topics_by_unit: Dict[str, List[DetectedTopic]]  # unit_title -> topics

    # Confidence scores
    confidence_scores: Dict[str, float]  # topic_title -> confidence

    # Manual adjustments (if creator provides feedback)
    manual_adjustments: List[Dict[str, Any]]

    # Errors and warnings
    errors: List[str]
    warnings: List[str]

    # Status
    analysis_complete: bool
    awaiting_approval: bool


def create_initial_structure_state(
    course_id: str,
    course_title: str,
    content_chunks: List[Dict[str, Any]],
) -> StructureState:
    """
    Create an initial Structure Analysis state.

    Args:
        course_id: ID of the course being analyzed
        course_title: Title of the course
        content_chunks: Ingested content chunks to analyze

    Returns:
        Initial StructureState
    """
    return StructureState(
        course_id=course_id,
        course_title=course_title,
        content_chunks=content_chunks,
        phase="analyze_content",
        detected_topics=[],
        total_topics=0,
        detected_units=[],
        total_units=0,
        topic_relationships=[],
        prerequisite_map={},
        structure_hierarchy={},
        topics_by_unit={},
        confidence_scores={},
        manual_adjustments=[],
        errors=[],
        warnings=[],
        analysis_complete=False,
        awaiting_approval=False,
    )
