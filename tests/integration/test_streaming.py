"""Integration tests for POST /api/v1/query/stream — SSE streaming path.

Covers:
  - Normal streaming flow (sub_query → token → done)
  - Monotonic sequence numbering
  - X-Request-ID propagation into SSE chunks
  - Error chunk emission on agent failure
  - Timeout error chunk
  - Conversation turn persistence only on full completion
  - 403 on thread ownership mismatch
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from aim.schemas.provenance import ProvenanceMap, SourceReference, SourceType
from aim.schemas.query import CostInfo, QueryResponse, StreamChunk


# ── Helpers ──────────────────────────────────────────────────────────────────

def _chunks(query_id=None) -> list[StreamChunk]:
    """Build a realistic sequence of StreamChunk events."""
    qid = query_id or uuid4()
    return [
        StreamChunk(chunk_type="sub_query", content="[1] architecture overview", query_id=qid, sequence=0),
        StreamChunk(chunk_type="sub_query", content="Retrieved 5 sources. Synthesizing…", query_id=qid, sequence=1),
        StreamChunk(chunk_type="token", content="AIM uses ", query_id=qid, sequence=2),
        StreamChunk(chunk_type="token", content="a graph-backed RAG pipeline.", query_id=qid, sequence=3),
        StreamChunk(
            chunk_type="done",
            content="",
            query_id=qid,
            sequence=4,
            sources=[{"id": "s1", "title": "Architecture"}],
            confidence=0.92,
            cost_info=CostInfo(input_tokens=100, output_tokens=50, embedding_tokens=30, estimated_cost_usd=0.005),
        ),
    ]


async def _async_gen(chunks):
    """Turn a list into an async generator."""
    for c in chunks:
        yield c


def _parse_sse_events(body: str) -> list[dict]:
    """Parse SSE text into list of JSON dicts."""
    events = []
    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ── Tests ────────────────────────────────────────────────────────────────────

async def test_stream_returns_sse_events(client):
    """A normal streaming request yields sub_query, token, and done SSE events."""
    qid = uuid4()
    chunks = _chunks(qid)

    async def _fake_stream(**kwargs):
        for c in chunks:
            yield c

    with (
        patch("aim.agents.reasoning_agent.stream_reasoning_agent", side_effect=_fake_stream),
        patch("aim.api.routes.query.get_response_cache", return_value=MagicMock()),
        patch("aim.api.routes.query.get_conversation_store", return_value=MagicMock()),
    ):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "What is the architecture?", "query_id": str(qid)},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    events = _parse_sse_events(response.text)
    assert len(events) == 5
    types = [e["chunk_type"] for e in events]
    assert types == ["sub_query", "sub_query", "token", "token", "done"]


async def test_stream_monotonic_sequence(client):
    """SSE chunks must carry monotonically increasing sequence numbers."""
    qid = uuid4()
    chunks = _chunks(qid)

    async def _fake_stream(**kwargs):
        for c in chunks:
            yield c

    with (
        patch("aim.agents.reasoning_agent.stream_reasoning_agent", side_effect=_fake_stream),
        patch("aim.api.routes.query.get_response_cache", return_value=MagicMock()),
        patch("aim.api.routes.query.get_conversation_store", return_value=MagicMock()),
    ):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "Sequence numbering test", "query_id": str(qid)},
        )

    events = _parse_sse_events(response.text)
    seqs = [e["sequence"] for e in events]
    assert seqs == list(range(len(events)))


async def test_stream_propagates_request_id(client):
    """X-Request-ID header must appear in every SSE chunk."""
    qid = uuid4()
    chunks = _chunks(qid)

    async def _fake_stream(**kwargs):
        for c in chunks:
            yield c

    with (
        patch("aim.agents.reasoning_agent.stream_reasoning_agent", side_effect=_fake_stream),
        patch("aim.api.routes.query.get_response_cache", return_value=MagicMock()),
        patch("aim.api.routes.query.get_conversation_store", return_value=MagicMock()),
    ):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "Request ID propagation test", "query_id": str(qid)},
            headers={"X-Request-ID": "req-test-123"},
        )

    events = _parse_sse_events(response.text)
    for event in events:
        assert event.get("request_id") == "req-test-123"


async def test_stream_error_on_agent_failure(client):
    """When the agent raises, the route must emit an error SSE chunk."""

    async def _failing_stream(**kwargs):
        raise RuntimeError("agent exploded")
        yield  # make it a generator  # noqa: unreachable

    with (
        patch("aim.agents.reasoning_agent.stream_reasoning_agent", side_effect=_failing_stream),
        patch("aim.api.routes.query.get_response_cache", return_value=MagicMock()),
        patch("aim.api.routes.query.get_conversation_store", return_value=MagicMock()),
    ):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "Trigger agent error"},
        )

    assert response.status_code == 200  # SSE always 200, error in payload
    events = _parse_sse_events(response.text)
    assert any(e["chunk_type"] == "error" for e in events)
    # Must not leak internal error details
    for e in events:
        if e["chunk_type"] == "error":
            assert "exploded" not in e["content"]


async def test_stream_timeout_emits_error_chunk(client, monkeypatch):
    """Route timeout must produce a timeout error SSE event."""
    from aim.config import get_settings

    # Patch the timeout on the real settings instance (keeps auth working)
    settings = get_settings()
    monkeypatch.setattr(settings, "route_timeout_seconds", 0.1)

    async def _slow_stream(**kwargs):
        await asyncio.sleep(999)
        yield StreamChunk(chunk_type="token", content="never", query_id=uuid4(), sequence=0)

    with (
        patch("aim.agents.reasoning_agent.stream_reasoning_agent", side_effect=_slow_stream),
        patch("aim.api.routes.query.get_response_cache", return_value=MagicMock()),
        patch("aim.api.routes.query.get_conversation_store", return_value=MagicMock()),
    ):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "Timeout test"},
        )

    events = _parse_sse_events(response.text)
    timeout_events = [e for e in events if e["chunk_type"] == "error" and "timed out" in e["content"].lower()]
    assert len(timeout_events) >= 1


async def test_stream_persists_turn_on_completion(client):
    """When thread_id is set and stream completes, the turn must be saved."""
    qid = uuid4()
    tid = uuid4()
    chunks = _chunks(qid)

    async def _fake_stream(**kwargs):
        for c in chunks:
            yield c

    mock_store = MagicMock()
    mock_store.get_history_for_key = AsyncMock(return_value=[])
    mock_store.append_turn = AsyncMock()

    with (
        patch("aim.agents.reasoning_agent.stream_reasoning_agent", side_effect=_fake_stream),
        patch("aim.api.routes.query.get_response_cache", return_value=MagicMock()),
        patch("aim.api.routes.query.get_conversation_store", return_value=mock_store),
    ):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "Save my turn", "query_id": str(qid), "thread_id": str(tid)},
        )

    assert response.status_code == 200
    mock_store.append_turn.assert_called_once()
    call_kwargs = mock_store.append_turn.call_args
    assert call_kwargs.kwargs["thread_id"] == tid


async def test_stream_does_not_persist_on_error(client):
    """On agent error, the conversation turn must NOT be persisted."""

    async def _failing_stream(**kwargs):
        yield StreamChunk(chunk_type="token", content="partial", query_id=uuid4(), sequence=0)
        raise RuntimeError("mid-stream failure")

    mock_store = MagicMock()
    mock_store.get_history_for_key = AsyncMock(return_value=[])
    mock_store.append_turn = AsyncMock()

    with (
        patch("aim.agents.reasoning_agent.stream_reasoning_agent", side_effect=_failing_stream),
        patch("aim.api.routes.query.get_response_cache", return_value=MagicMock()),
        patch("aim.api.routes.query.get_conversation_store", return_value=mock_store),
    ):
        await client.post(
            "/api/v1/query/stream",
            json={"query": "Fail mid-stream", "thread_id": str(uuid4())},
        )

    mock_store.append_turn.assert_not_called()


async def test_stream_without_thread_does_not_persist(client):
    """Stateless streaming queries must not touch the conversation store."""
    qid = uuid4()
    chunks = _chunks(qid)

    async def _fake_stream(**kwargs):
        for c in chunks:
            yield c

    mock_store = MagicMock()
    mock_store.append_turn = AsyncMock()

    with (
        patch("aim.agents.reasoning_agent.stream_reasoning_agent", side_effect=_fake_stream),
        patch("aim.api.routes.query.get_response_cache", return_value=MagicMock()),
        patch("aim.api.routes.query.get_conversation_store", return_value=mock_store),
    ):
        await client.post(
            "/api/v1/query/stream",
            json={"query": "Stateless stream", "query_id": str(qid)},
        )

    mock_store.append_turn.assert_not_called()


async def test_stream_403_on_thread_ownership_mismatch(client):
    """Thread belonging to another key must return 403 before streaming."""
    mock_store = MagicMock()
    mock_store.get_history_for_key = AsyncMock(
        side_effect=PermissionError("belongs to different key")
    )

    with (
        patch("aim.api.routes.query.get_response_cache", return_value=MagicMock()),
        patch("aim.api.routes.query.get_conversation_store", return_value=mock_store),
    ):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "Ownership check", "thread_id": str(uuid4())},
        )

    assert response.status_code == 403


async def test_stream_done_event_carries_metadata(client):
    """The done SSE event must include sources, confidence, and cost_info."""
    qid = uuid4()
    chunks = _chunks(qid)

    async def _fake_stream(**kwargs):
        for c in chunks:
            yield c

    with (
        patch("aim.agents.reasoning_agent.stream_reasoning_agent", side_effect=_fake_stream),
        patch("aim.api.routes.query.get_response_cache", return_value=MagicMock()),
        patch("aim.api.routes.query.get_conversation_store", return_value=MagicMock()),
    ):
        response = await client.post(
            "/api/v1/query/stream",
            json={"query": "Metadata check", "query_id": str(qid)},
        )

    events = _parse_sse_events(response.text)
    done = [e for e in events if e["chunk_type"] == "done"][0]
    assert done["confidence"] == pytest.approx(0.92)
    assert done["sources"] is not None
    assert done["cost_info"]["input_tokens"] == 100


async def test_stream_uses_exact_incident_fast_path(client):
    """Direct incident recall should stream structured graph facts, not the agent."""
    qid = uuid4()
    source = SourceReference(
        source_type=SourceType.NEO4J_GRAPH,
        uri="neo4j://node/inc-100",
        title="INC-2025-100",
        content_snippet="INC-2025-100 was reported by SRE Team",
        confidence=0.98,
    )
    fast_response = QueryResponse(
        query_id=qid,
        original_query="What happened with INC-2025-100 and who is on it?",
        answer="INC-2025-100: Auth Service rate limiter returning 429s.",
        provenance=ProvenanceMap(
            query_id=qid,
            sources={source.source_id: source},
            overall_confidence=0.98,
        ),
        model_used="structured_exact_incident",
        latency_ms=15.0,
        cost_info=CostInfo(),
    )

    async def _unexpected_stream(**kwargs):
        raise AssertionError("stream_reasoning_agent should not run")
        yield  # make it an async generator  # noqa: unreachable

    with (
        patch("aim.api.routes.query._try_exact_incident_response", AsyncMock(return_value=fast_response)),
        patch("aim.agents.reasoning_agent.stream_reasoning_agent", side_effect=_unexpected_stream),
        patch("aim.api.routes.query.get_response_cache", return_value=MagicMock()),
        patch("aim.api.routes.query.get_conversation_store", return_value=MagicMock()),
    ):
        response = await client.post(
            "/api/v1/query/stream",
            json={
                "query": "What happened with INC-2025-100 and who is on it?",
                "query_id": str(qid),
            },
        )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert [e["chunk_type"] for e in events] == ["sub_query", "token", "done"]
    assert "Auth Service rate limiter" in events[1]["content"]
    assert events[2]["provenance"]["sources"]
