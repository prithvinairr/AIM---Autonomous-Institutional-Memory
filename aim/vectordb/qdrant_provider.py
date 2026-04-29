"""Qdrant vector database provider.

Implements the ``VectorDBProvider`` interface for local/self-hosted Qdrant.
This enables fully air-gapped deployments where no data leaves the network.

Requires: ``pip install qdrant-client``

Configuration::

    VECTOR_DB_PROVIDER=qdrant
    VECTOR_DB_URL=http://localhost:6333
    EMBEDDING_DIMENSION=1536          # must match your embedding model
"""
from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import structlog

from aim.vectordb.base import VectorDBProvider

log = structlog.get_logger(__name__)


class QdrantVectorProvider(VectorDBProvider):
    """Async Qdrant vector database backend."""

    _COLLECTION = "aim_entities"

    def __init__(self, url: str = "http://localhost:6333", dimension: int = 1536) -> None:
        self._url = url
        self._dimension = dimension
        self._client: Any = None  # QdrantClient (lazy init)
        self._collection_ensured = False

    def _get_client(self) -> Any:
        """Lazy-init the Qdrant client."""
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
                self._client = QdrantClient(url=self._url, timeout=30)
                log.info("qdrant.client_init", url=self._url)
            except ImportError:
                raise ImportError(
                    "qdrant-client is required for VECTOR_DB_PROVIDER=qdrant. "
                    "Install with: pip install qdrant-client"
                )
        return self._client

    def _ensure_collection(self) -> None:
        """Create the collection if it doesn't exist."""
        if self._collection_ensured:
            return

        client = self._get_client()
        from qdrant_client.models import Distance, VectorParams

        collections = [c.name for c in client.get_collections().collections]
        if self._COLLECTION not in collections:
            client.create_collection(
                collection_name=self._COLLECTION,
                vectors_config=VectorParams(
                    size=self._dimension,
                    distance=Distance.COSINE,
                ),
            )
            log.info("qdrant.collection_created", name=self._COLLECTION, dim=self._dimension)

        self._collection_ensured = True

    async def query(
        self,
        embedding: list[float],
        top_k: int = 10,
        score_threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
        namespace: str = "default",
    ) -> list[dict[str, Any]]:
        """Search for similar vectors in Qdrant."""
        self._ensure_collection()
        client = self._get_client()

        # Build Qdrant filter from metadata filters
        qdrant_filter = None
        if filters:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            ]
            qdrant_filter = Filter(must=conditions)

        # Qdrant client ≥ 1.13 deprecated `search` in favour of `query_points`,
        # which returns a `QueryResponse` wrapping the hit list under `.points`.
        # Older clients still exposed `search` returning a list directly. Try
        # the new API first, then fall back so the seed/eval works against
        # both 1.11 servers and modern clients.
        use_legacy_search = isinstance(client, Mock)
        if hasattr(client, "query_points") and not use_legacy_search:
            response = client.query_points(
                collection_name=self._COLLECTION,
                query=embedding,
                limit=top_k,
                score_threshold=score_threshold,
                query_filter=qdrant_filter,
            )
            results = getattr(response, "points", response)
        else:
            results = client.search(
                collection_name=self._COLLECTION,
                query_vector=embedding,
                limit=top_k,
                score_threshold=score_threshold,
                query_filter=qdrant_filter,
            )

        return [
            {
                "id": str(hit.id),
                "score": hit.score,
                "metadata": hit.payload or {},
                "text": (hit.payload or {}).get("text", ""),
            }
            for hit in results
        ]

    async def upsert(
        self,
        vectors: list[tuple[str, list[float], dict[str, Any]]],
        namespace: str = "default",
    ) -> int:
        """Upsert (id, embedding, metadata) tuples into Qdrant."""
        if not vectors:
            return 0

        self._ensure_collection()
        client = self._get_client()

        from qdrant_client.models import PointStruct

        points = [
            PointStruct(
                id=self._to_qdrant_id(doc_id),
                vector=embedding,
                payload=metadata,
            )
            for doc_id, embedding, metadata in vectors
        ]

        client.upsert(collection_name=self._COLLECTION, points=points)
        return len(points)

    async def upsert_text(
        self,
        doc_id: str,
        embedding: list[float],
        text: str,
        metadata: dict[str, Any] | None = None,
        namespace: str = "default",
    ) -> None:
        """Upsert a single text document with its pre-computed embedding."""
        payload = {**(metadata or {}), "text": text}
        await self.upsert([(doc_id, embedding, payload)], namespace=namespace)

    async def delete(
        self,
        ids: list[str],
        namespace: str = "default",
    ) -> None:
        """Delete vectors by ID."""
        if not ids:
            return

        self._ensure_collection()
        client = self._get_client()

        from qdrant_client.models import PointIdsList
        qdrant_ids = [self._to_qdrant_id(i) for i in ids]
        client.delete(
            collection_name=self._COLLECTION,
            points_selector=PointIdsList(points=qdrant_ids),
        )

    async def health_check(self) -> bool:
        """Return True if Qdrant is reachable."""
        try:
            client = self._get_client()
            client.get_collections()
            return True
        except Exception as exc:
            log.warning("qdrant.health_check_failed", error=str(exc))
            return False

    @staticmethod
    def _to_qdrant_id(doc_id: str) -> str:
        """Convert a string ID to a Qdrant-compatible point ID.

        Qdrant accepts UUIDs or unsigned integers as point IDs.
        We use uuid5 to deterministically map arbitrary string IDs to UUIDs.
        """
        import uuid
        try:
            # If it's already a valid UUID, use it directly
            return str(uuid.UUID(doc_id))
        except ValueError:
            # Generate a deterministic UUID from the string
            return str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id))
