"""Student Vector Store - Per Student, Per Course

This manages ChromaDB collections for a student's personal data:
- qna_history: Student's Q&A for personalization
- explanations: Cached explanations
- misconceptions: Common mistakes for this student
- learning_style: Preference data
- feedback: Student feelings about course/difficulty/pace
- interactions: All student interactions for context
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma

from ..core.config import Settings, get_settings
from .embeddings import get_embeddings


class StudentVectorStore:
    """
    Vector store for a student's personal learning data.

    Structure: ./data/vector_db/students/student_{id}/course_{id}/

    Collections per course:
    - qna_history: Student's Q&A for personalization
    - explanations: Cached explanations
    - misconceptions: Common mistakes for this student
    - learning_style: Preference data
    """

    # Collection names
    COLLECTION_QNA_HISTORY = "qna_history"
    COLLECTION_EXPLANATIONS = "explanations"
    COLLECTION_MISCONCEPTIONS = "misconceptions"
    COLLECTION_LEARNING_STYLE = "learning_style"
    COLLECTION_FEEDBACK = "feedback"  # Student feelings about course
    COLLECTION_INTERACTIONS = "interactions"  # All interactions for context

    def __init__(self, student_id: int, settings: Settings | None = None):
        """
        Initialize the Student Vector Store.

        Args:
            student_id: The unique student identifier
            settings: Application settings (uses default if None)
        """
        self.student_id = student_id
        self.settings = settings or get_settings()

        # Base path for this student
        self.base_path = Path(self.settings.STUDENT_VECTOR_DB_PATH) / f"student_{student_id}"
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_course_path(self, course_id: int) -> Path:
        """Get the path for a specific course."""
        return self.base_path / f"course_{course_id}"

    def _get_client(self, course_id: int) -> chromadb.PersistentClient:
        """Get or create a ChromaDB client for a specific course."""
        course_path = self._get_course_path(course_id)
        course_path.mkdir(parents=True, exist_ok=True)

        return chromadb.PersistentClient(
            path=str(course_path),
            settings=Settings(anonymized_telemetry=False)
        )

    def get_or_create_collection(
        self,
        student_id: int,
        course_id: int,
        collection_name: str
    ) -> chromadb.Collection:
        """Get or create a collection for a student's course."""
        client = self._get_client(course_id)
        return client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def get_vector_store(
        self,
        student_id: int,
        course_id: int,
        collection_name: str
    ) -> Chroma:
        """Get a LangChain Chroma vector store."""
        client = self._get_client(course_id)
        embedding_service = get_embeddings()

        return Chroma(
            client=client,
            collection_name=collection_name,
            embedding_function=embedding_service.embed_text,
            collection_metadata={"hnsw:space": "cosine"}
        )

    # ==================================================================
    # Q&A History Methods
    # ==================================================================

    async def add_qa_interaction(
        self,
        student_id: int,
        course_id: int,
        topic_id: int,
        question: str,
        answer: str,
        was_correct: bool,
        follow_up_needed: bool = False
    ) -> str:
        """
        Add a Q&A interaction to the history.

        Used for personalization - remembering what the student asked
        and how they answered.
        """
        vector_store = self.get_vector_store(student_id, course_id, self.COLLECTION_QNA_HISTORY)

        interaction_id = f"qa_{student_id}_{course_id}_{topic_id}_{hash(answer) % 10000:04d}"

        metadata = {
            "student_id": str(student_id),
            "course_id": str(course_id),
            "topic_id": str(topic_id),
            "timestamp": str(__import__('time').time()),
            "was_correct": str(was_correct),
            "follow_up_needed": str(follow_up_needed),
        }

        vector_store.add_texts(
            texts=[f"Q: {question}\nA: {answer}"],
            metadatas=[metadata],
            ids=[interaction_id]
        )

        return interaction_id

    async def get_student_qa_history(
        self,
        student_id: int,
        course_id: int,
        topic_id: int | None = None,
        k: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent Q&A history for a student in a course."""
        vector_store = self.get_vector_store(student_id, course_id, self.COLLECTION_QNA_HISTORY)

        # Query by topic if specified
        filter_metadata = None
        if topic_id is not None:
            filter_metadata = {"topic_id": str(topic_id)}

        # Get collection for raw querying
        collection = self.get_or_create_collection(student_id, course_id, self.COLLECTION_QNA_HISTORY)
        embedding_service = get_embeddings()

        # Simple query (get recent interactions)
        results = collection.get(
            limit=k,
            where=filter_metadata
        )

        formatted = []
        for doc in results:
            formatted.append({
                "id": doc.id,
                "content": doc.metadata.get("page_content", ""),
                "metadata": doc.metadata
            })

        return formatted

    # ==================================================================
    # Explanations Methods
    # ==================================================================

    async def cache_explanation(
        self,
        student_id: int,
        course_id: int,
        topic_id: int,
        explanation: str,
        style_used: str = "default"
    ) -> str:
        """Cache an explanation for reuse."""
        vector_store = self.get_vector_store(student_id, course_id, self.COLLECTION_EXPLANATIONS)

        explanation_id = f"exp_{student_id}_{course_id}_{topic_id}_{hash(explanation) % 10000:04d}"

        metadata = {
            "student_id": str(student_id),
            "course_id": str(course_id),
            "topic_id": str(topic_id),
            "style_used": style_used,
            "timestamp": str(__import__('time').time()),
        }

        vector_store.add_texts(
            texts=[explanation],
            metadatas=[metadata],
            ids=[explanation_id]
        )

        return explanation_id

    async def get_cached_explanations(
        self,
        student_id: int,
        course_id: int,
        topic_id: int,
        k: int = 3
    ) -> List[Dict[str, Any]]:
        """Get previously given explanations for this topic."""
        vector_store = self.get_vector_store(student_id, course_id, self.COLLECTION_EXPLANATIONS)

        collection = self.get_or_create_collection(student_id, course_id, self.COLLECTION_EXPLANATIONS)
        embedding_service = get_embeddings()

        # Find similar explanations
        results = collection.peek(limit=k)

        formatted = []
        for doc in results:
            formatted.append({
                "id": doc.id,
                "explanation": doc.metadata.get("page_content", ""),
                "metadata": doc.metadata
            })

        return formatted

    # ==================================================================
    # Misconceptions Methods
    # ==================================================================

    async def record_misconception(
        self,
        student_id: int,
        course_id: int,
        topic_id: int,
        concept: str,
        misconception: str
    ) -> str:
        """
        Record a misconception for this student.

        Increments frequency if this misconception has been seen before.
        """
        vector_store = self.get_vector_store(student_id, course_id, self.COLLECTION_MISCONCEPTIONS)

        # Check if this misconception already exists
        existing = self.find_misconception(student_id, course_id, concept, misconception)

        if existing:
            # Increment frequency
            # TODO: Update frequency in database
            pass
        else:
            # Create new misconception record
            misconception_id = f"misc_{student_id}_{course_id}_{hash(misconception) % 10000:04d}"

            metadata = {
                "student_id": str(student_id),
                "course_id": str(course_id),
                "topic_id": str(topic_id),
                "concept": concept,
                "misconception": misconception,
                "frequency": "1",
                "last_seen": str(__import__('time').time()),
            }

            vector_store.add_texts(
                texts=[f"Misconception: {misconception}"],
                metadatas=[metadata],
                ids=[misconception_id]
            )

        return misconception_id

    def find_misconception(
        self,
        student_id: int,
        course_id: int,
        concept: str,
        misconception: str
    ) -> bool:
        """Check if this misconception already exists for the student."""
        collection = self.get_or_create_collection(student_id, course_id, self.COLLECTION_MISCONCEPTIONS)

        # Simple check for existence
        results = collection.get(
            where={
                "student_id": str(student_id),
                "concept": concept,
                "misconception": misconception
            },
            limit=1
        )

        return len(results) > 0

    async def get_student_misconceptions(
        self,
        student_id: int,
        course_id: int,
        topic_id: int | None = None
    ) -> List[Dict[str, Any]]:
        """Get all misconceptions for a student in a course."""
        collection = self.get_or_create_collection(student_id, course_id, self.COLLECTION_MISCONCEPTIONS)

        filter_metadata = {"student_id": str(student_id)}
        if topic_id is not None:
            filter_metadata["topic_id"] = str(topic_id)

        results = collection.get(where=filter_metadata, limit=100)

        formatted = []
        for doc in results:
            formatted.append({
                "id": doc.id,
                "content": doc.metadata.get("page_content", ""),
                "metadata": doc.metadata
            })

        return formatted

    # ==================================================================
    # Learning Style Methods
    # ==================================================================

    async def update_learning_style(
        self,
        student_id: int,
        course_id: int,
        preferences: Dict[str, Any]
    ) -> None:
        """Store/update student learning preferences."""
        vector_store = self.get_vector_store(student_id, course_id, self.COLLECTION_LEARNING_STYLE)

        # Store as a text document for retrieval
        preference_text = f"Learning preferences: {preferences}"

        metadata = {
            "student_id": str(student_id),
            "course_id": str(course_id),
            "timestamp": str(__import__('time').time()),
        }

        vector_store.add_texts(
            texts=[preference_text],
            metadatas=[metadata],
            ids=[f"style_{student_id}_{course_id}"]
        )

    async def get_learning_style(
        self,
        student_id: int,
        course_id: int
    ) -> Dict[str, Any] | None:
        """Get student's learning preferences."""
        collection = self.get_or_create_collection(student_id, course_id, self.COLLECTION_LEARNING_STYLE)

        results = collection.get(
            where={
                "student_id": str(student_id),
                "course_id": str(course_id)
            },
            limit=1
        )

        if results:
            doc = results[0]
            # Extract preferences from stored JSON
            import json
            content = doc.metadata.get("page_content", "")
            if content.startswith("Learning preferences: "):
                return json.loads(content.replace("Learning preferences: ", ""))
        return None

    # ==================================================================
    # Feedback Methods (Student Feelings)
    # ==================================================================

    async def record_feedback(
        self,
        student_id: int,
        course_id: int,
        feedback_type: str,  # difficulty, pace, clarity, engagement, overall
        feedback_value: str,  # Free text or rating
        sentiment: Optional[str] = None,  # positive, neutral, negative
        topic_id: Optional[int] = None
    ) -> str:
        """
        Record student feedback about the course.

        Captures feelings like:
        - "This is too hard"
        - "I'm bored, go faster"
        - "I don't understand this topic"
        - "This is great!"

        Used for personalization and adapting to student needs.
        """
        vector_store = self.get_vector_store(student_id, course_id, self.COLLECTION_FEEDBACK)

        feedback_id = f"feed_{student_id}_{course_id}_{feedback_type}_{int(__import__('time').time())}"

        metadata = {
            "student_id": str(student_id),
            "course_id": str(course_id),
            "feedback_type": feedback_type,
            "timestamp": str(__import__('time').time()),
        }

        if sentiment:
            metadata["sentiment"] = sentiment
        if topic_id:
            metadata["topic_id"] = str(topic_id)

        vector_store.add_texts(
            texts=[feedback_value],
            metadatas=[metadata],
            ids=[feedback_id]
        )

        return feedback_id

    async def get_recent_feedback(
        self,
        student_id: int,
        course_id: int,
        feedback_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent feedback from the student."""
        collection = self.get_or_create_collection(student_id, course_id, self.COLLECTION_FEEDBACK)

        where = {"student_id": str(student_id), "course_id": str(course_id)}
        if feedback_type:
            where["feedback_type"] = feedback_type

        try:
            results = collection.get(where=where, limit=limit)

            formatted = []
            for doc in results:
                formatted.append({
                    "id": doc.id,
                    "content": doc.metadata.get("page_content", ""),
                    "metadata": doc.metadata
                })

            return formatted
        except Exception:
            return []

    async def get_student_sentiment_summary(
        self,
        student_id: int,
        course_id: int
    ) -> Dict[str, Any]:
        """
        Get a summary of student's recent sentiment about the course.

        Returns overall sentiment and specific issues/concerns.
        """
        collection = self.get_or_create_collection(student_id, course_id, self.COLLECTION_FEEDBACK)

        try:
            results = collection.get(
                where={"student_id": str(student_id), "course_id": str(course_id)},
                limit=50
            )

            positive = 0
            negative = 0
            neutral = 0
            concerns = []

            for doc in results:
                metadata = doc.metadata
                sentiment = metadata.get("sentiment", "neutral")
                feedback_type = metadata.get("feedback_type", "")
                content = doc.metadata.get("page_content", "")

                if sentiment == "positive":
                    positive += 1
                elif sentiment == "negative":
                    negative += 1
                    # Track negative feedback for follow-up
                    if feedback_type in ["difficulty", "clarity"]:
                        concerns.append({
                            "type": feedback_type,
                            "content": content,
                        })
                else:
                    neutral += 1

            total = positive + negative + neutral
            overall_sentiment = "neutral"
            if total > 0:
                positive_ratio = positive / total
                negative_ratio = negative / total
                if positive_ratio > 0.6:
                    overall_sentiment = "positive"
                elif negative_ratio > 0.4:
                    overall_sentiment = "negative"

            return {
                "overall_sentiment": overall_sentiment,
                "positive_count": positive,
                "negative_count": negative,
                "neutral_count": neutral,
                "concerns": concerns,
                "total_feedback": total,
            }

        except Exception:
            return {
                "overall_sentiment": "neutral",
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "concerns": [],
                "total_feedback": 0,
            }

    # ==================================================================
    # Interaction Methods (General Context)
    # ==================================================================

    async def record_interaction(
        self,
        student_id: int,
        course_id: int,
        interaction_type: str,  # question, explanation, quiz, hint, review, video_progress
        content: str,
        topic_id: Optional[int] = None,
        additional_metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Record a general interaction with the student.

        This provides full context for the AI to understand:
        - What has the student done?
        - When did they do it?
        - How did they respond?
        - What's their engagement level?

        Used for:
        - Contextualizing current questions
        - Understanding learning patterns
        - Identifying when to intervene
        """
        vector_store = self.get_vector_store(student_id, course_id, self.COLLECTION_INTERACTIONS)

        interaction_id = f"inter_{student_id}_{course_id}_{int(__import__('time').time())}"

        metadata = {
            "student_id": str(student_id),
            "course_id": str(course_id),
            "interaction_type": interaction_type,
            "timestamp": str(__import__('time').time()),
        }

        if topic_id:
            metadata["topic_id"] = str(topic_id)
        if additional_metadata:
            metadata.update({k: str(v) for k, v in additional_metadata.items()})

        vector_store.add_texts(
            texts=[content],
            metadatas=[metadata],
            ids=[interaction_id]
        )

        return interaction_id

    async def get_recent_interactions(
        self,
        student_id: int,
        course_id: int,
        interaction_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get recent interactions for context."""
        collection = self.get_or_create_collection(student_id, course_id, self.COLLECTION_INTERACTIONS)

        where = {"student_id": str(student_id), "course_id": str(course_id)}
        if interaction_type:
            where["interaction_type"] = interaction_type

        try:
            results = collection.get(where=where, limit=limit)

            formatted = []
            for doc in results:
                formatted.append({
                    "id": doc.id,
                    "content": doc.metadata.get("page_content", ""),
                    "metadata": doc.metadata
                })

            return formatted
        except Exception:
            return []

    # ==================================================================
    # Utility Methods
    # ==================================================================

    def get_all_collections_stats(
        self,
        student_id: int
    ) -> Dict[str, Dict[str, int]]:
        """Get statistics for all collections across all courses for a student."""
        stats = {}

        student_path = Path(self.settings.STUDENT_VECTOR_DB_PATH) / f"student_{student_id}"
        if not student_path.exists():
            return stats

        # Iterate through course directories
        for course_dir in student_path.iterdir():
            if course_dir.is_dir() and course_dir.name.startswith("course_"):
                course_id = int(course_dir.name.replace("course_", ""))

                # Get stats for each collection
                course_stats = {}
                collections = [
                    self.COLLECTION_QNA_HISTORY,
                    self.COLLECTION_EXPLANATIONS,
                    self.COLLECTION_MISCONCEPTIONS,
                    self.COLLECTION_LEARNING_STYLE,
                    self.COLLECTION_FEEDBACK,
                    self.COLLECTION_INTERACTIONS,
                ]

                for coll_name in collections:
                    try:
                        client = self._get_client(course_id)
                        collection = client.get_collection(name=coll_name)
                        course_stats[coll_name] = collection.count()
                    except Exception:
                        course_stats[coll_name] = 0

                stats[str(course_id)] = course_stats

        return stats

    def delete_student_data(self) -> None:
        """Delete all data for a student."""
        import shutil

        if self.base_path.exists():
            shutil.rmtree(self.base_path)

        # Reinitialize
        self.base_path.mkdir(parents=True, exist_ok=True)
