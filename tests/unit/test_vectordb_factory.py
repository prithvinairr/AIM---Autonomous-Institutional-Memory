"""Tests for the vector database factory — including Qdrant path."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from aim.vectordb.factory import get_vectordb_provider, reset_vectordb_provider


@pytest.fixture(autouse=True)
def _reset():
    reset_vectordb_provider()
    yield
    reset_vectordb_provider()


def test_pinecone_provider(env_vars, monkeypatch):
    """VECTOR_DB_PROVIDER=pinecone creates a PineconeVectorProvider.

    Note: post-δ.3 A+ the default flipped from pinecone → qdrant for
    sovereignty, so this test explicitly opts in to pinecone.
    """
    monkeypatch.setenv("VECTOR_DB_PROVIDER", "pinecone")

    from aim.config import get_settings
    get_settings.cache_clear()

    from aim.vectordb.pinecone_provider import PineconeVectorProvider
    provider = get_vectordb_provider()
    assert isinstance(provider, PineconeVectorProvider)


def test_default_is_qdrant(env_vars):
    """Default (post-δ.3 A+) is qdrant — local-first sovereignty."""
    from aim.vectordb.qdrant_provider import QdrantVectorProvider
    provider = get_vectordb_provider()
    assert isinstance(provider, QdrantVectorProvider)


def test_qdrant_provider(env_vars, monkeypatch):
    """VECTOR_DB_PROVIDER=qdrant creates a QdrantVectorProvider."""
    monkeypatch.setenv("VECTOR_DB_PROVIDER", "qdrant")
    monkeypatch.setenv("VECTOR_DB_URL", "http://localhost:6333")

    from aim.config import get_settings
    get_settings.cache_clear()

    from aim.vectordb.qdrant_provider import QdrantVectorProvider
    provider = get_vectordb_provider()
    assert isinstance(provider, QdrantVectorProvider)


def test_local_provider_uses_qdrant(env_vars, monkeypatch):
    """VECTOR_DB_PROVIDER=local also routes to QdrantVectorProvider."""
    monkeypatch.setenv("VECTOR_DB_PROVIDER", "local")

    from aim.config import get_settings
    get_settings.cache_clear()

    from aim.vectordb.qdrant_provider import QdrantVectorProvider
    provider = get_vectordb_provider()
    assert isinstance(provider, QdrantVectorProvider)


def test_invalid_provider(env_vars, monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PROVIDER", "weaviate")

    from aim.config import get_settings
    get_settings.cache_clear()

    with pytest.raises(Exception, match="vector_db_provider"):
        get_vectordb_provider()


def test_singleton(env_vars):
    p1 = get_vectordb_provider()
    p2 = get_vectordb_provider()
    assert p1 is p2
