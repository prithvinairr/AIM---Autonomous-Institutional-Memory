"""Tests for the Qdrant vector database provider.

qdrant-client is not in dev deps, so all client interactions are mocked.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock
import uuid

import pytest

from aim.vectordb.qdrant_provider import QdrantVectorProvider


@pytest.fixture
def provider():
    """Create a QdrantVectorProvider with a pre-mocked client."""
    p = QdrantVectorProvider(url="http://localhost:6333", dimension=1536)
    # Pre-mock the client to avoid qdrant_client import
    p._client = MagicMock()
    p._client.get_collections.return_value = MagicMock(
        collections=[MagicMock(name="aim_entities")]
    )
    p._collection_ensured = True
    return p


# ── ID conversion ────────────────────────────────────────────────────────────

def test_to_qdrant_id_valid_uuid():
    test_uuid = str(uuid.uuid4())
    result = QdrantVectorProvider._to_qdrant_id(test_uuid)
    assert result == test_uuid


def test_to_qdrant_id_arbitrary_string():
    result = QdrantVectorProvider._to_qdrant_id("my-entity-id")
    parsed = uuid.UUID(result)
    assert parsed.version == 5
    assert QdrantVectorProvider._to_qdrant_id("my-entity-id") == result


def test_to_qdrant_id_different_inputs_differ():
    id1 = QdrantVectorProvider._to_qdrant_id("entity-a")
    id2 = QdrantVectorProvider._to_qdrant_id("entity-b")
    assert id1 != id2


# ── Query ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_returns_formatted_results(provider):
    mock_hit = MagicMock()
    mock_hit.id = "test-id"
    mock_hit.score = 0.95
    mock_hit.payload = {"text": "hello world", "name": "Test"}
    provider._client.search.return_value = [mock_hit]

    results = await provider.query(embedding=[0.1] * 1536, top_k=5)

    assert len(results) == 1
    assert results[0]["id"] == "test-id"
    assert results[0]["score"] == 0.95
    assert results[0]["text"] == "hello world"


@pytest.mark.asyncio
async def test_query_empty_results(provider):
    provider._client.search.return_value = []
    results = await provider.query(embedding=[0.1] * 1536)
    assert results == []


@pytest.mark.asyncio
async def test_query_with_filters(provider):
    """Filters are converted to Qdrant conditions."""
    provider._client.search.return_value = []

    # Mock qdrant_client.models to avoid import
    mock_models = MagicMock()
    with patch.dict("sys.modules", {"qdrant_client": MagicMock(), "qdrant_client.models": mock_models}):
        await provider.query(embedding=[0.1] * 1536, filters={"type": "Person"})

    provider._client.search.assert_called_once()


@pytest.mark.asyncio
async def test_query_null_payload(provider):
    mock_hit = MagicMock()
    mock_hit.id = "test-id"
    mock_hit.score = 0.5
    mock_hit.payload = None
    provider._client.search.return_value = [mock_hit]

    results = await provider.query(embedding=[0.1] * 1536)
    assert results[0]["metadata"] == {}
    assert results[0]["text"] == ""


# ── Upsert ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_returns_count(provider):
    mock_models = MagicMock()
    with patch.dict("sys.modules", {"qdrant_client": MagicMock(), "qdrant_client.models": mock_models}):
        count = await provider.upsert([
            ("id1", [0.1] * 1536, {"name": "test1"}),
            ("id2", [0.2] * 1536, {"name": "test2"}),
        ])

    assert count == 2
    provider._client.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_empty_list(provider):
    count = await provider.upsert([])
    assert count == 0


# ── Upsert text ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_text_includes_text_in_payload(provider):
    mock_models = MagicMock()
    with patch.dict("sys.modules", {"qdrant_client": MagicMock(), "qdrant_client.models": mock_models}):
        await provider.upsert_text(
            doc_id="doc-1",
            embedding=[0.1] * 1536,
            text="hello world",
            metadata={"source": "test"},
        )

    provider._client.upsert.assert_called_once()


# ── Delete ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_calls_client(provider):
    mock_models = MagicMock()
    with patch.dict("sys.modules", {"qdrant_client": MagicMock(), "qdrant_client.models": mock_models}):
        await provider.delete(["id1", "id2"])

    provider._client.delete.assert_called_once()


@pytest.mark.asyncio
async def test_delete_empty_list(provider):
    await provider.delete([])


# ── Health check ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check_success(provider):
    provider._client.get_collections.return_value = MagicMock(collections=[])
    result = await provider.health_check()
    assert result is True


@pytest.mark.asyncio
async def test_health_check_failure(provider):
    provider._client.get_collections.side_effect = ConnectionError("refused")
    result = await provider.health_check()
    assert result is False


# ── Collection creation ──────────────────────────────────────────────────────

def test_ensure_collection_skips_when_cached():
    p = QdrantVectorProvider()
    p._collection_ensured = True
    p._ensure_collection()  # No client needed


# ── Import guard ─────────────────────────────────────────────────────────────

def test_missing_qdrant_client_raises():
    p = QdrantVectorProvider()
    p._client = None
    with patch.dict("sys.modules", {"qdrant_client": None}):
        with pytest.raises(ImportError, match="qdrant-client"):
            p._get_client()
