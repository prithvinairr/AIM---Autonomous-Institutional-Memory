"""Tests for VectorDB provider abstraction layer."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.vectordb.base import VectorDBProvider
from aim.vectordb.factory import get_vectordb_provider, reset_vectordb_provider
from aim.vectordb.pinecone_provider import PineconeVectorProvider


# ── ABC contract ─────────────────────────────────────────────────────────────


class TestVectorDBProviderABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            VectorDBProvider()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all(self):
        class Incomplete(VectorDBProvider):
            pass

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]


# ── PineconeVectorProvider ───────────────────────────────────────────────────


class TestPineconeVectorProvider:
    @patch("aim.vectordb.pinecone_provider.PineconeClient")
    def test_delegates_query(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.query_with_embedding.return_value = [{"id": "1", "score": 0.9}]
        mock_client_cls.return_value = mock_client

        provider = PineconeVectorProvider()
        provider._client = mock_client

        import asyncio
        results = asyncio.get_event_loop().run_until_complete(
            provider.query(embedding=[0.1] * 1536, top_k=5)
        )
        mock_client.query_with_embedding.assert_called_once()
        assert len(results) == 1

    @patch("aim.vectordb.pinecone_provider.PineconeClient")
    def test_delegates_upsert(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.upsert.return_value = 1
        mock_client_cls.return_value = mock_client

        provider = PineconeVectorProvider()
        provider._client = mock_client

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            provider.upsert(vectors=[("d1", [0.1] * 1536, {"title": "test"})])
        )
        mock_client.upsert.assert_called_once()

    @patch("aim.vectordb.pinecone_provider.PineconeClient")
    def test_delegates_upsert_text(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.upsert.return_value = 1
        mock_client_cls.return_value = mock_client

        provider = PineconeVectorProvider()
        provider._client = mock_client

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            provider.upsert_text(doc_id="d1", embedding=[0.1] * 1536, text="hello", metadata={})
        )
        mock_client.upsert.assert_called_once()

    @patch("aim.vectordb.pinecone_provider.PineconeClient")
    def test_delegates_delete(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client

        provider = PineconeVectorProvider()
        provider._client = mock_client

        import asyncio
        asyncio.get_event_loop().run_until_complete(provider.delete(ids=["d1"]))
        mock_client.delete.assert_called_once()

    @patch("aim.vectordb.pinecone_provider.PineconeClient")
    def test_health_check(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.health_check.return_value = True
        mock_client_cls.return_value = mock_client

        provider = PineconeVectorProvider()
        provider._client = mock_client

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(provider.health_check())
        assert result is True


# ── Factory ──────────────────────────────────────────────────────────────────


class TestVectorDBFactory:
    def setup_method(self):
        reset_vectordb_provider()

    def teardown_method(self):
        reset_vectordb_provider()

    @patch("aim.config.get_settings")
    def test_default_returns_pinecone(self, mock_settings):
        mock_settings.return_value = MagicMock(vector_db_provider="pinecone")
        provider = get_vectordb_provider()
        assert isinstance(provider, PineconeVectorProvider)

    @patch("aim.config.get_settings")
    def test_singleton_returns_same_instance(self, mock_settings):
        mock_settings.return_value = MagicMock(vector_db_provider="pinecone")
        p1 = get_vectordb_provider()
        p2 = get_vectordb_provider()
        assert p1 is p2

    @patch("aim.config.get_settings")
    def test_qdrant_returns_qdrant_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            vector_db_provider="qdrant", vector_db_url="http://localhost:6333",
            embedding_dimension=1536,
        )
        from aim.vectordb.qdrant_provider import QdrantVectorProvider
        provider = get_vectordb_provider()
        assert isinstance(provider, QdrantVectorProvider)

    @patch("aim.config.get_settings")
    def test_local_returns_qdrant_provider(self, mock_settings):
        mock_settings.return_value = MagicMock(
            vector_db_provider="local", vector_db_url="",
            embedding_dimension=1536,
        )
        from aim.vectordb.qdrant_provider import QdrantVectorProvider
        provider = get_vectordb_provider()
        assert isinstance(provider, QdrantVectorProvider)

    @patch("aim.config.get_settings")
    def test_reset_clears_singleton(self, mock_settings):
        mock_settings.return_value = MagicMock(vector_db_provider="pinecone")
        p1 = get_vectordb_provider()
        reset_vectordb_provider()
        p2 = get_vectordb_provider()
        assert p1 is not p2
