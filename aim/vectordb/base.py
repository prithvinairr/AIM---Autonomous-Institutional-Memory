"""Abstract base for pluggable vector database providers.

Mirrors the ``aim.llm.base`` pattern: a clean ABC that any vector DB
(Pinecone, Qdrant, Weaviate, Milvus, pgvector, in-memory) can implement.

Embedding logic is intentionally excluded — that lives in ``EmbeddingProvider``
so consumers can batch-embed once and fan out to any vector DB.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VectorDBProvider(ABC):
    """Interface for pluggable vector database backends."""

    @abstractmethod
    async def query(
        self,
        embedding: list[float],
        top_k: int = 10,
        score_threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
        namespace: str = "default",
    ) -> list[dict[str, Any]]:
        """Search for similar vectors.

        Returns list of dicts with keys: id, score, metadata, text.
        """

    @abstractmethod
    async def upsert(
        self,
        vectors: list[tuple[str, list[float], dict[str, Any]]],
        namespace: str = "default",
    ) -> int:
        """Upsert (id, embedding, metadata) tuples. Returns count upserted."""

    @abstractmethod
    async def upsert_text(
        self,
        doc_id: str,
        embedding: list[float],
        text: str,
        metadata: dict[str, Any] | None = None,
        namespace: str = "default",
    ) -> None:
        """Upsert a single text document with its pre-computed embedding."""

    @abstractmethod
    async def delete(
        self,
        ids: list[str],
        namespace: str = "default",
    ) -> None:
        """Delete vectors by ID."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the vector store is reachable."""
