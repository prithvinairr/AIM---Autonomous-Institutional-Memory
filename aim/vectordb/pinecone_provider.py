"""Pinecone implementation of VectorDBProvider.

Thin adapter over the existing PineconeClient — delegates all I/O to the
battle-tested singleton index and thread-pool executor pattern.
"""
from __future__ import annotations

from typing import Any

from aim.vectordb.base import VectorDBProvider
from aim.vectordb.pinecone_client import PineconeClient


class PineconeVectorProvider(VectorDBProvider):
    """VectorDBProvider backed by Pinecone."""

    def __init__(self) -> None:
        self._client = PineconeClient()

    async def query(
        self,
        embedding: list[float],
        top_k: int = 10,
        score_threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
        namespace: str = "default",
    ) -> list[dict[str, Any]]:
        return await self._client.query_with_embedding(
            embedding,
            top_k=top_k,
            score_threshold=score_threshold,
            filters=filters,
            namespace=namespace,
        )

    async def upsert(
        self,
        vectors: list[tuple[str, list[float], dict[str, Any]]],
        namespace: str = "default",
    ) -> int:
        return await self._client.upsert(vectors, namespace=namespace)

    async def upsert_text(
        self,
        doc_id: str,
        embedding: list[float],
        text: str,
        metadata: dict[str, Any] | None = None,
        namespace: str = "default",
    ) -> None:
        meta = {"text": text[:40960], **(metadata or {})}
        await self._client.upsert([(doc_id, embedding, meta)], namespace=namespace)

    async def delete(
        self,
        ids: list[str],
        namespace: str = "default",
    ) -> None:
        await self._client.delete(ids, namespace=namespace)

    async def health_check(self) -> bool:
        return await self._client.health_check()
