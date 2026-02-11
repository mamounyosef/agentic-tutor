"""Constructor Vector Store - Per Course

This manages ChromaDB collections for:
- content_chunks: All material chunks with embeddings
- topics: Topic summaries
- quiz_questions: Quiz with embeddings for similarity
- structure: Course structure metadata
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_community.vectorstores import Chroma as LangChainChroma

from ..core.config import Settings as AppSettings, get_settings
from .embeddings import get_embeddings


class ConstructorVectorStore:
    """
    Vector store for course construction.

    One collection per course, stored in:
    ./data/vector_db/constructor/course_{id}/
    """

    # Collection names
    COLLECTION_CONTENT_CHUNKS = "content_chunks"
    COLLECTION_TOPICS = "topics"
    COLLECTION_QUESTIONS = "quiz_questions"
    COLLECTION_STRUCTURE = "structure"

    def __init__(self, course_id: int, settings: AppSettings | None = None):
        """
        Initialize the Constructor Vector Store for a specific course.

        Args:
            course_id: The unique course identifier
            settings: Application settings (uses default if None)
        """
        self.course_id = course_id
        self.settings = settings or get_settings()

        # Course-specific path
        self.persist_dir = Path(
            self.settings.CONSTRUCTOR_VECTOR_DB_PATH
        ) / f"course_{course_id}"

        # Ensure directory exists
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client for this course
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # Initialize LangChain wrapper
        self.vector_store: Optional[Chroma] = None

    def get_or_create_collection(self, collection_name: str) -> chromadb.Collection:
        """Get or create a ChromaDB collection."""
        return self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def get_vector_store(
        self,
        collection_name: str,
        embedding_function=None
    ) -> LangChainChroma:
        """
        Get or create a LangChain Chroma vector store.

        Args:
            collection_name: Name of the collection
            embedding_function: Optional custom embedding function

        Returns:
            LangChainChroma vector store instance
        """
        # Get embeddings from our service
        if embedding_function is None:
            embedding_service = get_embeddings()
            embedding_function = embedding_service.embeddings

        return LangChainChroma(
            client=self.client,
            collection_name=collection_name,
            embedding_function=embedding_function,
            collection_metadata={"hnsw:space": "cosine"}
        )

    async def add_content_chunks(
        self,
        chunks: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Add content chunks to the vector store.

        Args:
            chunks: List of chunks with keys:
                - text: The text content
                - metadata: Dict with course_id, unit_id, topic_id, etc.

        Returns:
            List of chunk IDs
        """
        vector_store = self.get_vector_store(self.COLLECTION_CONTENT_CHUNKS)

        documents = []
        ids = []

        for i, chunk in enumerate(chunks):
            doc_id = f"chunk_{self.course_id}_{i}_{hash(chunk['text']) % 10000:04d}"
            ids.append(doc_id)

            # Prepare metadata
            metadata = {
                "course_id": str(self.course_id),
                "chunk_type": chunk.get("chunk_type", "content"),
                "source_file": chunk.get("source_file", ""),
            }

            # Add optional metadata
            if "unit_id" in chunk:
                metadata["unit_id"] = str(chunk["unit_id"])
            if "topic_id" in chunk:
                metadata["topic_id"] = str(chunk["topic_id"])
            if "page_number" in chunk:
                metadata["page_number"] = str(chunk["page_number"])

            documents.append({
                "page_content": chunk["text"],
                "metadata": metadata
            })

        # Add to vector store
        vector_store.add_texts(
            texts=[doc["page_content"] for doc in documents],
            metadatas=[doc["metadata"] for doc in documents],
            ids=ids
        )

        return ids

    async def add_topic_summaries(
        self,
        topics: List[Dict[str, Any]]
    ) -> List[str]:
        """Add topic summaries to the vector store."""
        vector_store = self.get_vector_store(self.COLLECTION_TOPICS)

        documents = []
        ids = []

        for topic in topics:
            doc_id = f"topic_{topic['id']}"
            ids.append(doc_id)

            metadata = {
                "course_id": str(self.course_id),
                "unit_id": str(topic.get("unit_id", "")),
                "topic_id": str(topic["id"]),
                "title": topic.get("title", ""),
            }

            documents.append({
                "page_content": topic.get("summary", topic.get("description", "")),
                "metadata": metadata
            })

        vector_store.add_texts(
            texts=[doc["page_content"] for doc in documents],
            metadatas=[doc["metadata"] for doc in documents],
            ids=ids
        )

        return ids

    async def add_quiz_questions(
        self,
        questions: List[Dict[str, Any]]
    ) -> List[str]:
        """Add quiz questions to the vector store for similarity checking."""
        vector_store = self.get_vector_store(self.COLLECTION_QUESTIONS)

        documents = []
        ids = []

        for question in questions:
            doc_id = f"question_{question['id']}"
            ids.append(doc_id)

            metadata = {
                "course_id": str(self.course_id),
                "topic_id": str(question.get("topic_id", "")),
                "question_type": question.get("question_type", ""),
                "difficulty": question.get("difficulty", "medium"),
            }

            documents.append({
                "page_content": question.get("question_text", ""),
                "metadata": metadata
            })

        vector_store.add_texts(
            texts=[doc["page_content"] for doc in documents],
            metadatas=[doc["metadata"] for doc in documents],
            ids=ids
        )

        return ids

    def similarity_search(
        self,
        query: str,
        collection_name: str,
        k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search on a collection.

        Args:
            query: Search query text
            collection_name: Collection to search
            k: Number of results to return
            filter_metadata: Optional metadata filter

        Returns:
            List of matching documents with metadata
        """
        collection = self.get_or_create_collection(collection_name)

        # Embed the query
        embedding_service = get_embeddings()
        query_embedding = embedding_service.embed_text(query)

        # Search
        where_clause = filter_metadata
        if isinstance(filter_metadata, dict) and len(filter_metadata) > 1:
            has_operator = any(str(k).startswith("$") for k in filter_metadata.keys())
            if not has_operator:
                where_clause = {"$and": [{k: v} for k, v in filter_metadata.items()]}

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where=where_clause,
        )

        # Format results
        formatted_results = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, doc in enumerate(documents):
            metadata = metadatas[i] if i < len(metadatas) and metadatas[i] else {}
            distance = distances[i] if i < len(distances) else None
            doc_id = ids[i] if i < len(ids) else f"doc_{i}"
            formatted_results.append({
                "id": doc_id,
                "content": doc or "",
                "metadata": metadata,
                "distance": distance
            })

        return formatted_results

    def get_collection_stats(self) -> Dict[str, int]:
        """Get statistics about all collections for this course."""
        stats = {}

        collections = [
            self.COLLECTION_CONTENT_CHUNKS,
            self.COLLECTION_TOPICS,
            self.COLLECTION_QUESTIONS,
            self.COLLECTION_STRUCTURE,
        ]

        for coll_name in collections:
            try:
                collection = self.get_or_create_collection(coll_name)
                stats[coll_name] = collection.count()
            except Exception:
                stats[coll_name] = 0

        return stats

    def delete_course_data(self) -> None:
        """Delete all data for this course (useful for rebuilds)."""
        import shutil

        # Delete the entire course directory
        if self.persist_dir.exists():
            shutil.rmtree(self.persist_dir)

        # Reinitialize
        self.persist_dir.mkdir(parents=True, exist_ok=True)
