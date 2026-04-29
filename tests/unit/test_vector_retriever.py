"""Unit tests for the vector retriever node."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from aim.agents.nodes.vector_retriever import retrieve_vectors
from aim.agents.state import AgentState
from aim.schemas.query import ReasoningDepth


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> AgentState:
    defaults = {
        "query_id": uuid4(),
        "original_query": "test query",
        "reasoning_depth": ReasoningDepth.STANDARD,
        "sub_queries": ["What is X?", "Who owns Y?"],
    }
    defaults.update(overrides)
    return AgentState(**defaults)


def _mock_settings(**overrides):
    defaults = {
        "top_k_vectors": 10,
        "similarity_threshold": 0.75,
        "node_timeout_seconds": 20.0,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _make_matches(ids: list[str], scores: list[float] | None = None):
    scores = scores or [0.9] * len(ids)
    return [
        {"id": vid, "score": s, "metadata": {"text": f"Content for {vid}", "title": f"Doc {vid}"}}
        for vid, s in zip(ids, scores)
    ]


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_returns_unchanged_state_when_no_sub_queries():
    state = _make_state(sub_queries=[])
    result = await retrieve_vectors(state)
    assert result.vector_snippets == []


@pytest.mark.asyncio
async def test_batch_embeds_all_sub_queries():
    embeddings = [[0.1] * 10, [0.2] * 10]
    matches_q1 = _make_matches(["v1", "v2"])
    matches_q2 = _make_matches(["v3"])

    mock_client = MagicMock()
    mock_client.batch_embed = AsyncMock(return_value=(embeddings, 100))
    mock_client.query_with_embedding = AsyncMock(
        side_effect=[matches_q1, matches_q2]
    )

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(
        side_effect=[
            (embeddings, 100),         # batch_embed
            matches_q1,                 # query 1
            matches_q2,                 # query 2
        ]
    )

    with patch("aim.agents.nodes.vector_retriever.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.vector_retriever.PineconeClient", return_value=mock_client):
            with patch("aim.agents.nodes.vector_retriever.get_breaker", return_value=mock_breaker):
                state = _make_state()
                result = await retrieve_vectors(state)

    # batch_embed (1 call) + 2 query calls = 3
    assert mock_breaker.call.call_count == 3
    assert result.embedding_tokens == 100


@pytest.mark.asyncio
async def test_deduplicates_vector_ids_across_sub_queries():
    embeddings = [[0.1] * 10, [0.2] * 10]
    # Same vector ID returned for both sub-queries
    matches = _make_matches(["shared-vec"])

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(
        side_effect=[
            (embeddings, 50),
            matches,
            matches,  # same ID returned
        ]
    )

    mock_client = MagicMock()

    with patch("aim.agents.nodes.vector_retriever.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.vector_retriever.PineconeClient", return_value=mock_client):
            with patch("aim.agents.nodes.vector_retriever.get_breaker", return_value=mock_breaker):
                state = _make_state()
                result = await retrieve_vectors(state)

    # Deduplicated: only 1 snippet despite appearing in both results
    assert len(result.vector_snippets) == 1


@pytest.mark.asyncio
async def test_creates_source_references_with_pinecone_type():
    embeddings = [[0.1] * 10]
    matches = _make_matches(["v1"], scores=[0.88])

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(
        side_effect=[(embeddings, 50), matches]
    )

    mock_client = MagicMock()

    with patch("aim.agents.nodes.vector_retriever.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.vector_retriever.PineconeClient", return_value=mock_client):
            with patch("aim.agents.nodes.vector_retriever.get_breaker", return_value=mock_breaker):
                state = _make_state(sub_queries=["Q1"])
                result = await retrieve_vectors(state)

    assert len(result.sources) == 1
    src = next(iter(result.sources.values()))
    assert src.source_type.value == "pinecone_vector"
    assert src.confidence == 0.88


@pytest.mark.asyncio
async def test_tracks_per_sub_query_attribution():
    embeddings = [[0.1] * 10, [0.2] * 10]
    matches_q1 = _make_matches(["v1"])
    matches_q2 = _make_matches(["v2"])

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(
        side_effect=[(embeddings, 50), matches_q1, matches_q2]
    )

    mock_client = MagicMock()

    with patch("aim.agents.nodes.vector_retriever.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.vector_retriever.PineconeClient", return_value=mock_client):
            with patch("aim.agents.nodes.vector_retriever.get_breaker", return_value=mock_breaker):
                state = _make_state(sub_queries=["Q1", "Q2"])
                result = await retrieve_vectors(state)

    assert "Q1" in result.sub_query_source_map
    assert "Q2" in result.sub_query_source_map
    assert len(result.sub_query_source_map["Q1"]) == 1
    assert len(result.sub_query_source_map["Q2"]) == 1


@pytest.mark.asyncio
async def test_circuit_open_on_embed_adds_reasoning_step():
    from aim.utils.circuit_breaker import CircuitOpenError

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(side_effect=CircuitOpenError("pinecone"))

    mock_client = MagicMock()

    with patch("aim.agents.nodes.vector_retriever.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.vector_retriever.PineconeClient", return_value=mock_client):
            with patch("aim.agents.nodes.vector_retriever.get_breaker", return_value=mock_breaker):
                state = _make_state(sub_queries=["Q1"])
                result = await retrieve_vectors(state)

    assert any("circuit open" in step.lower() for step in result.reasoning_steps)


@pytest.mark.asyncio
async def test_accumulates_embedding_tokens():
    embeddings = [[0.1] * 10]
    matches = _make_matches(["v1"])

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(
        side_effect=[(embeddings, 200), matches]
    )

    mock_client = MagicMock()

    with patch("aim.agents.nodes.vector_retriever.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.vector_retriever.PineconeClient", return_value=mock_client):
            with patch("aim.agents.nodes.vector_retriever.get_breaker", return_value=mock_breaker):
                state = _make_state(sub_queries=["Q1"], embedding_tokens=50)
                result = await retrieve_vectors(state)

    assert result.embedding_tokens == 250  # 50 existing + 200 new


@pytest.mark.asyncio
async def test_empty_matches_still_adds_reasoning_step():
    embeddings = [[0.1] * 10]

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(
        side_effect=[(embeddings, 10), []]  # no matches
    )

    mock_client = MagicMock()

    with patch("aim.agents.nodes.vector_retriever.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.vector_retriever.PineconeClient", return_value=mock_client):
            with patch("aim.agents.nodes.vector_retriever.get_breaker", return_value=mock_breaker):
                state = _make_state(sub_queries=["Q1"])
                result = await retrieve_vectors(state)

    assert any("Vector search" in step for step in result.reasoning_steps)
    assert result.vector_snippets == []


@pytest.mark.asyncio
async def test_confidence_is_clamped_to_0_1():
    embeddings = [[0.1] * 10]
    # Score > 1.0 should be clamped
    matches = [{"id": "v1", "score": 1.5, "metadata": {"text": "test"}}]

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(
        side_effect=[(embeddings, 10), matches]
    )

    mock_client = MagicMock()

    with patch("aim.agents.nodes.vector_retriever.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.vector_retriever.PineconeClient", return_value=mock_client):
            with patch("aim.agents.nodes.vector_retriever.get_breaker", return_value=mock_breaker):
                state = _make_state(sub_queries=["Q1"])
                result = await retrieve_vectors(state)

    src = next(iter(result.sources.values()))
    assert src.confidence <= 1.0


# ── Coverage: _query_one CircuitOpenError / TimeoutError (lines 56-62) ──────


@pytest.mark.asyncio
async def test_query_one_circuit_open_returns_empty_list():
    """CircuitOpenError in _query_one returns (sub_q, [])."""
    from aim.agents.nodes.vector_retriever import _query_one
    from aim.utils.circuit_breaker import CircuitOpenError

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(side_effect=CircuitOpenError("pinecone"))
    mock_provider = AsyncMock()

    with patch("aim.agents.nodes.vector_retriever.get_breaker", return_value=mock_breaker):
        sub_q, matches = await _query_one(
            sub_q="What is X?",
            embedding=[0.1] * 10,
            provider=mock_provider,
            top_k=10,
            score_threshold=0.75,
            filters=None,
            node_timeout=5.0,
        )

    assert sub_q == "What is X?"
    assert matches == []


@pytest.mark.asyncio
async def test_query_one_timeout_returns_empty_list():
    """TimeoutError in _query_one returns (sub_q, [])."""
    from aim.agents.nodes.vector_retriever import _query_one

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_provider = AsyncMock()

    with patch("aim.agents.nodes.vector_retriever.get_breaker", return_value=mock_breaker):
        sub_q, matches = await _query_one(
            sub_q="Who owns Y?",
            embedding=[0.2] * 10,
            provider=mock_provider,
            top_k=5,
            score_threshold=0.7,
            filters=None,
            node_timeout=5.0,
        )

    assert sub_q == "Who owns Y?"
    assert matches == []


# ── Coverage: retrieve_vectors general exception (lines 164-167) ────────────


@pytest.mark.asyncio
async def test_retrieve_vectors_general_exception_adds_reasoning_step():
    """Unexpected exception in retrieve_vectors is caught, logged, and added to reasoning_steps."""
    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(side_effect=RuntimeError("unexpected failure"))

    mock_client = MagicMock()
    mock_vdb = MagicMock()

    with patch("aim.agents.nodes.vector_retriever.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.vector_retriever.PineconeClient", return_value=mock_client):
            with patch("aim.agents.nodes.vector_retriever.get_breaker", return_value=mock_breaker):
                with patch("aim.agents.nodes.vector_retriever.get_vectordb_provider", return_value=mock_vdb):
                    state = _make_state(sub_queries=["Q1"])
                    result = await retrieve_vectors(state)

    # The error should be captured in reasoning_steps, not raised
    assert any("non-fatal" in step.lower() or "failed" in step.lower() for step in result.reasoning_steps)
    assert any("unexpected failure" in step for step in result.reasoning_steps)
