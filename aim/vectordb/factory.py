"""Factory for pluggable vector database providers.

Reads ``VECTOR_DB_PROVIDER`` from settings to select the implementation.
Follows the same singleton pattern as ``aim.llm.factory``.
"""
from __future__ import annotations

import structlog

from aim.vectordb.base import VectorDBProvider

log = structlog.get_logger(__name__)

_vectordb_instance: VectorDBProvider | None = None


def get_vectordb_provider() -> VectorDBProvider:
    """Return the configured VectorDBProvider (singleton)."""
    global _vectordb_instance
    if _vectordb_instance is not None:
        return _vectordb_instance

    from aim.config import get_settings
    settings = get_settings()
    provider_type = settings.vector_db_provider.lower()

    if provider_type == "pinecone":
        from aim.vectordb.pinecone_provider import PineconeVectorProvider
        _vectordb_instance = PineconeVectorProvider()
        log.info("vectordb.provider_init", provider="pinecone", index=settings.pinecone_index_name)
    elif provider_type in ("qdrant", "local"):
        from aim.vectordb.qdrant_provider import QdrantVectorProvider
        url = settings.vector_db_url or "http://localhost:6333"
        _vectordb_instance = QdrantVectorProvider(
            url=url,
            dimension=settings.embedding_dimension,
        )
        log.info("vectordb.provider_init", provider="qdrant", url=url, dim=settings.embedding_dimension)
    else:
        raise ValueError(
            f"Unknown vector_db_provider: {provider_type!r}. "
            "Supported: 'pinecone', 'qdrant', 'local'."
        )

    return _vectordb_instance


def reset_vectordb_provider() -> None:
    """Reset singleton — for tests only."""
    global _vectordb_instance
    _vectordb_instance = None
