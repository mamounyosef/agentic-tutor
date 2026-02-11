"""RAG (Retrieval-Augmented Generation) tools for Tutor agents.

These tools enable:
- Retrieving relevant course content for explanations
- Searching student's personal Q&A history
- Finding similar explanations given before
- Getting context for personalized responses
"""

import logging
from typing import Any, Dict, List, Optional


from app.vector.constructor_store import ConstructorVectorStore
from app.vector.student_store import StudentVectorStore, get_student_store

logger = logging.getLogger(__name__)


# =============================================================================
# Course Content Retrieval (Read-Only from Constructor's DB)
# =============================================================================

async def retrieve_topic_content(
    student_id: int,
    course_id: int,
    topic_id: int,
    query: str,
    k: int = 5
) -> Dict[str, Any]:
    """
    Retrieve relevant content from the course for a specific topic.

    This searches the course's vector DB (read-only) to find content
    relevant to the student's question or current topic.

    Args:
        student_id: The student's ID
        course_id: The course's ID
        topic_id: The topic to retrieve content for
        query: The query/question to find relevant content for
        k: Number of chunks to retrieve

    Returns:
        Dictionary with relevant content chunks and metadata
    """
    try:
        # Access Constructor's course vector DB (read-only)
        course_store = ConstructorVectorStore(course_id)

        # Search content chunks for this topic
        results = course_store.similarity_search(
            query=query,
            collection_name=ConstructorVectorStore.COLLECTION_CONTENT_CHUNKS,
            k=k,
            filter_metadata={"topic_id": str(topic_id)}
        )

        return {
            "success": True,
            "topic_id": topic_id,
            "query": query,
            "chunks": results,
            "chunk_count": len(results),
        }

    except Exception as e:
        logger.error(f"Error retrieving topic content: {e}")
        return {
            "success": False,
            "error": str(e),
            "chunks": [],
            "chunk_count": 0,
        }


async def semantic_search_course(
    student_id: int,
    course_id: int,
    query: str,
    k: int = 5,
    search_all_topics: bool = True
) -> Dict[str, Any]:
    """
    Semantic search across the entire course content.

    Finds relevant content regardless of topic boundaries.
    Useful for cross-topic questions and finding related concepts.

    Args:
        student_id: The student's ID
        course_id: The course's ID
        query: The semantic search query
        k: Number of results to return
        search_all_topics: If True, search all topics (not filtered by topic_id)

    Returns:
        Dictionary with search results from across the course
    """
    try:
        course_store = ConstructorVectorStore(course_id)

        # Search across all content chunks
        filter_metadata = None if search_all_topics else {"course_id": str(course_id)}

        results = course_store.similarity_search(
            query=query,
            collection_name=ConstructorVectorStore.COLLECTION_CONTENT_CHUNKS,
            k=k,
            filter_metadata=filter_metadata
        )

        return {
            "success": True,
            "query": query,
            "results": results,
            "result_count": len(results),
        }

    except Exception as e:
        logger.error(f"Error in semantic search: {e}")
        return {
            "success": False,
            "error": str(e),
            "results": [],
            "result_count": 0,
        }


async def get_topic_summary(
    student_id: int,
    course_id: int,
    topic_id: int
) -> Dict[str, Any]:
    """
    Get the summary of a specific topic from the course.

    Args:
        student_id: The student's ID
        course_id: The course's ID
        topic_id: The topic to get summary for

    Returns:
        Topic summary and key concepts
    """
    try:
        course_store = ConstructorVectorStore(course_id)

        # Search topic summaries collection
        results = course_store.similarity_search(
            query="",  # Get all for this topic
            collection_name=ConstructorVectorStore.COLLECTION_TOPICS,
            k=1,
            filter_metadata={"topic_id": str(topic_id)}
        )

        if results:
            return {
                "success": True,
                "topic_id": topic_id,
                "summary": results[0].get("content", ""),
                "metadata": results[0].get("metadata", {}),
            }
        else:
            return {
                "success": False,
                "error": "Topic not found",
                "topic_id": topic_id,
            }

    except Exception as e:
        logger.error(f"Error getting topic summary: {e}")
        return {
            "success": False,
            "error": str(e),
            "topic_id": topic_id,
        }


# =============================================================================
# Student Personalization Retrieval
# =============================================================================

async def search_student_qna_history(
    student_id: int,
    course_id: int,
    query: str,
    topic_id: Optional[int] = None,
    k: int = 5
) -> Dict[str, Any]:
    """
    Search student's Q&A history for relevant context.

    Useful for:
    - Finding what the student asked before
    - Seeing what explanations worked
    - Identifying repeated struggles
    - Personalizing based on past interactions

    Args:
        student_id: The student's ID
        course_id: The course's ID
        query: The query to find relevant Q&A
        topic_id: Optional topic filter
        k: Number of results

    Returns:
        Relevant Q&A history entries
    """
    try:
        student_store = get_student_store(student_id, course_id)

        results = await student_store.search_qna_history(
            query=query,
            topic_id=topic_id,
            k=k
        )

        return {
            "success": True,
            "query": query,
            "history": results,
            "count": len(results),
        }

    except Exception as e:
        logger.error(f"Error searching Q&A history: {e}")
        return {
            "success": False,
            "error": str(e),
            "history": [],
            "count": 0,
        }


async def get_relevant_explanations(
    student_id: int,
    course_id: int,
    query: str,
    topic_id: Optional[int] = None,
    k: int = 3
) -> Dict[str, Any]:
    """
    Get previously given explanations that were effective for this student.

    Retrieves explanations that:
    - Were given to this student before
    - Worked well (high effectiveness rating)
    - Cover similar concepts

    Args:
        student_id: The student's ID
        course_id: The course's ID
        query: The query to find relevant explanations
        topic_id: Optional topic filter
        k: Number of results

    Returns:
        Relevant cached explanations
    """
    try:
        student_store = get_student_store(student_id, course_id)

        results = await student_store.get_relevant_explanations(
            query=query,
            topic_id=topic_id,
            k=k
        )

        return {
            "success": True,
            "query": query,
            "explanations": results,
            "count": len(results),
        }

    except Exception as e:
        logger.error(f"Error getting explanations: {e}")
        return {
            "success": False,
            "error": str(e),
            "explanations": [],
            "count": 0,
        }


async def get_student_misconceptions(
    student_id: int,
    course_id: int,
    query: str,
    topic_id: Optional[int] = None,
    k: int = 5
) -> Dict[str, Any]:
    """
    Get misconceptions this student has demonstrated.

    Useful for:
    - Anticipating where student might struggle
    - Addressing known misunderstandings
    - Tracking progress on overcoming misconceptions

    Args:
        student_id: The student's ID
        course_id: The course's ID
        query: Query to find relevant misconceptions
        topic_id: Optional topic filter
        k: Number of results

    Returns:
        Relevant misconceptions for this student
    """
    try:
        student_store = get_student_store(student_id, course_id)

        results = await student_store.get_relevant_misconceptions(
            query=query,
            topic_id=topic_id,
            k=k
        )

        return {
            "success": True,
            "query": query,
            "misconceptions": results,
            "count": len(results),
        }

    except Exception as e:
        logger.error(f"Error getting misconceptions: {e}")
        return {
            "success": False,
            "error": str(e),
            "misconceptions": [],
            "count": 0,
        }


async def get_student_context(
    student_id: int,
    course_id: int
) -> Dict[str, Any]:
    """
    Get comprehensive context about the student for personalization.

    Aggregates:
    - Learning style/preferences
    - Recent feedback and sentiment
    - Recent interactions
    - Misconceptions
    - Q&A patterns

    Args:
        student_id: The student's ID
        course_id: The course's ID

    Returns:
        Comprehensive student context for personalization
    """
    try:
        student_store = get_student_store(student_id, course_id)

        # Get learning style
        learning_style = await student_store.get_learning_style(
            student_id=student_id,
            course_id=course_id,
        )

        # Get recent sentiment
        sentiment_summary = await student_store.get_student_sentiment_summary(
            student_id=student_id,
            course_id=course_id,
        )

        # Get recent feedback
        recent_feedback = await student_store.get_recent_feedback(
            student_id=student_id,
            course_id=course_id,
            limit=5,
        )

        # Get recent interactions
        recent_interactions = await student_store.get_recent_interactions(
            student_id=student_id,
            course_id=course_id,
            limit=10,
        )

        # Get misconceptions
        misconceptions = await student_store.get_student_misconceptions(
            student_id=student_id,
            course_id=course_id,
        )

        return {
            "success": True,
            "student_id": student_id,
            "course_id": course_id,
            "learning_style": learning_style or {},
            "sentiment": sentiment_summary,
            "recent_feedback": recent_feedback,
            "recent_interactions": recent_interactions,
            "misconceptions": misconceptions,
        }

    except Exception as e:
        logger.error(f"Error getting student context: {e}")
        return {
            "success": False,
            "error": str(e),
            "student_id": student_id,
            "course_id": course_id,
        }


# =============================================================================
# Combined Retrieval (Course + Student)
# =============================================================================

async def retrieve_for_explanation(
    student_id: int,
    course_id: int,
    topic_id: int,
    student_query: str,
    include_student_context: bool = True
) -> Dict[str, Any]:
    """
    Combined retrieval for generating personalized explanations.

    Retrieves:
    1. Relevant course content for the topic
    2. Student's learning style
    3. Previous explanations that worked
    4. Known misconceptions to address

    Args:
        student_id: The student's ID
        course_id: The course's ID
        topic_id: The topic being explained
        student_query: What the student is asking
        include_student_context: Whether to include personalization data

    Returns:
        Combined context for generating personalized explanation
    """
    try:
        # Get course content
        course_content = await retrieve_topic_content(
            student_id=student_id,
            course_id=course_id,
            topic_id=topic_id,
            query=student_query,
            k=5
        )

        result = {
            "success": True,
            "course_content": course_content.get("chunks", []),
            "student_query": student_query,
            "topic_id": topic_id,
        }

        if include_student_context:
            # Get student context in parallel
            student_context = await get_student_context(
                student_id=student_id,
                course_id=course_id
            )

            result["student_context"] = student_context

        return result

    except Exception as e:
        logger.error(f"Error retrieving for explanation: {e}")
        return {
            "success": False,
            "error": str(e),
            "course_content": [],
            "student_query": student_query,
        }
