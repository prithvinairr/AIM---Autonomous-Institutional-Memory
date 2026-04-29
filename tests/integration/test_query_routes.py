"""Integration tests for /api/v1/query/* routes."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from aim.schemas.provenance import ProvenanceMap
from aim.schemas.query import QueryResponse, SubQueryResult


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_response() -> QueryResponse:
    qid = uuid4()
    prov = ProvenanceMap(
        query_id=qid,
        sources={},
        graph_nodes=[],
        sub_query_traces=[],
        citation_map={},
        overall_confidence=0.85,
        reasoning_steps=["decompose", "retrieve", "synthesize"],
    )
    return QueryResponse(
        query_id=qid,
        original_query="What is the AIM architecture?",
        answer="AIM uses a graph-backed RAG pipeline. [SRC:src-1]",
        sub_query_results=[
            SubQueryResult(
                sub_query_id="sq_0",
                sub_query_text="graph architecture",
                graph_hits=2,
                vector_hits=3,
                mcp_hits=1,
            )
        ],
        provenance=prov,
        model_used="claude-opus-4-6",
        latency_ms=1250.0,
    )


# ── POST /api/v1/query ────────────────────────────────────────────────────────

async def test_query_returns_200(client):
    mock_response = _make_response()

    with (
        patch(
            "aim.api.routes.query.run_reasoning_agent",
            AsyncMock(return_value=mock_response),
        ),
        patch("aim.api.routes.query.get_response_cache") as mock_cache_fn,
    ):
        mock_cache = MagicMock()
        mock_cache.set_tenanted = AsyncMock()
        mock_cache_fn.return_value = mock_cache

        response = await client.post(
            "/api/v1/query",
            json={"query": "What is the AIM architecture?"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "provenance" in data
    assert data["answer"] != ""


async def test_query_response_has_required_fields(client):
    mock_response = _make_response()

    with (
        patch(
            "aim.api.routes.query.run_reasoning_agent",
            AsyncMock(return_value=mock_response),
        ),
        patch("aim.api.routes.query.get_response_cache") as mock_cache_fn,
    ):
        mock_cache = MagicMock()
        mock_cache.set_tenanted = AsyncMock()
        mock_cache_fn.return_value = mock_cache

        response = await client.post(
            "/api/v1/query",
            json={"query": "What is the AIM architecture?"},
        )

    data = response.json()
    for field in ("query_id", "answer", "provenance", "model_used", "latency_ms"):
        assert field in data, f"Missing field: {field}"


async def test_query_with_stream_true_returns_400(client):
    response = await client.post(
        "/api/v1/query",
        json={"query": "Should I use stream?", "stream": True},
    )
    assert response.status_code == 400
    assert "stream" in response.json()["detail"].lower()


async def test_query_too_short_returns_422(client):
    response = await client.post(
        "/api/v1/query",
        json={"query": "ab"},  # min_length=3
    )
    assert response.status_code == 422


async def test_query_returns_500_on_agent_failure(client):
    with (
        patch(
            "aim.api.routes.query.run_reasoning_agent",
            AsyncMock(side_effect=RuntimeError("internal crash")),
        ),
        patch("aim.api.routes.query.get_response_cache") as mock_cache_fn,
    ):
        mock_cache_fn.return_value = MagicMock()

        response = await client.post(
            "/api/v1/query",
            json={"query": "Trigger an agent failure"},
        )

    assert response.status_code == 500
    # Internal error detail must not leak
    assert "internal crash" not in response.text


async def test_query_requires_api_key(test_app):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        # No X-API-Key header
    ) as anon:
        response = await anon.post(
            "/api/v1/query",
            json={"query": "Anonymous query attempt"},
        )
    assert response.status_code == 401


async def test_query_is_cached_after_execution(client):
    mock_response = _make_response()
    captured: list = []

    async def _fake_set(tenant_id, key, value):
        captured.append((key, value))

    with (
        patch(
            "aim.api.routes.query.run_reasoning_agent",
            AsyncMock(return_value=mock_response),
        ),
        patch("aim.api.routes.query.get_response_cache") as mock_cache_fn,
    ):
        mock_cache = MagicMock()
        mock_cache.set_tenanted = AsyncMock(side_effect=_fake_set)
        mock_cache_fn.return_value = mock_cache

        await client.post(
            "/api/v1/query",
            json={"query": "Cached query test"},
        )

    assert len(captured) == 1
    _, cached_value = captured[0]
    assert "answer" in cached_value


# ── GET /api/v1/query/{id} ────────────────────────────────────────────────────

async def test_get_cached_query_returns_200(client):
    mock_response = _make_response()
    cached_data = mock_response.model_dump(mode="json")

    with patch("aim.api.routes.query.get_response_cache") as mock_cache_fn:
        mock_cache = MagicMock()
        mock_cache.get_tenanted = AsyncMock(return_value=cached_data)
        mock_cache_fn.return_value = mock_cache

        response = await client.get(f"/api/v1/query/{mock_response.query_id}")

    assert response.status_code == 200
    assert response.json()["query_id"] == str(mock_response.query_id)


async def test_get_cached_query_returns_404_when_not_found(client):
    with patch("aim.api.routes.query.get_response_cache") as mock_cache_fn:
        mock_cache = MagicMock()
        mock_cache.get_tenanted = AsyncMock(return_value=None)
        mock_cache_fn.return_value = mock_cache

        response = await client.get(f"/api/v1/query/{uuid4()}")

    assert response.status_code == 404


# ── Anonymous mode ────────────────────────────────────────────────────────────

# ── Thread-aware queries ──────────────────────────────────────────────────────

async def test_query_with_thread_id_loads_history(client):
    """When thread_id is supplied, the route loads history from the store."""
    from uuid import uuid4 as _uuid4

    mock_response = _make_response()
    thread_id = _uuid4()
    captured_history: list = []

    async def _fake_agent(**kwargs):
        captured_history.extend(kwargs.get("conversation_history", []))
        return mock_response

    with (
        patch("aim.api.routes.query.run_reasoning_agent", side_effect=_fake_agent),
        patch("aim.api.routes.query.get_response_cache") as mock_cache_fn,
        patch("aim.api.routes.query.get_conversation_store") as mock_store_fn,
    ):
        mock_cache = MagicMock()
        mock_cache.set_tenanted = AsyncMock()
        mock_cache_fn.return_value = mock_cache

        mock_store = MagicMock()
        mock_store.get_history_for_key = AsyncMock(return_value=[
            {"role": "user", "content": "prior question"},
            {"role": "assistant", "content": "prior answer"},
        ])
        mock_store.append_turn = AsyncMock()
        mock_store_fn.return_value = mock_store

        response = await client.post(
            "/api/v1/query",
            json={"query": "Follow-up question here?", "thread_id": str(thread_id)},
        )

    assert response.status_code == 200
    assert captured_history == [
        {"role": "user", "content": "prior question"},
        {"role": "assistant", "content": "prior answer"},
    ]


async def test_query_with_thread_id_saves_turn(client):
    """A successful threaded query must persist the turn to the conversation store."""
    from uuid import uuid4 as _uuid4

    mock_response = _make_response()
    thread_id = _uuid4()
    saved_turns: list = []

    async def _capture_turn(**kwargs):
        saved_turns.append(kwargs)

    with (
        patch("aim.api.routes.query.run_reasoning_agent", AsyncMock(return_value=mock_response)),
        patch("aim.api.routes.query.get_response_cache") as mock_cache_fn,
        patch("aim.api.routes.query.get_conversation_store") as mock_store_fn,
    ):
        mock_cache = MagicMock()
        mock_cache.set_tenanted = AsyncMock()
        mock_cache_fn.return_value = mock_cache

        mock_store = MagicMock()
        mock_store.get_history_for_key = AsyncMock(return_value=[])
        mock_store.append_turn = AsyncMock(side_effect=_capture_turn)
        mock_store_fn.return_value = mock_store

        await client.post(
            "/api/v1/query",
            json={"query": "Save this turn please!", "thread_id": str(thread_id)},
        )

    assert len(saved_turns) == 1
    assert saved_turns[0]["thread_id"] == thread_id


async def test_query_with_thread_id_403_on_ownership_mismatch(client):
    """If the thread belongs to a different key, the route must return 403."""
    from uuid import uuid4 as _uuid4

    thread_id = _uuid4()

    with (
        patch("aim.api.routes.query.get_response_cache") as mock_cache_fn,
        patch("aim.api.routes.query.get_conversation_store") as mock_store_fn,
    ):
        mock_cache_fn.return_value = MagicMock()

        mock_store = MagicMock()
        mock_store.get_history_for_key = AsyncMock(
            side_effect=PermissionError("belongs to different key")
        )
        mock_store_fn.return_value = mock_store

        response = await client.post(
            "/api/v1/query",
            json={"query": "Ownership violation attempt", "thread_id": str(thread_id)},
        )

    assert response.status_code == 403


async def test_query_without_thread_id_does_not_touch_conv_store(client):
    """Stateless queries must never call the conversation store."""
    mock_response = _make_response()

    with (
        patch("aim.api.routes.query.run_reasoning_agent", AsyncMock(return_value=mock_response)),
        patch("aim.api.routes.query.get_response_cache") as mock_cache_fn,
        patch("aim.api.routes.query.get_conversation_store") as mock_store_fn,
    ):
        mock_cache = MagicMock()
        mock_cache.set_tenanted = AsyncMock()
        mock_cache_fn.return_value = mock_cache

        mock_store = MagicMock()
        mock_store.get_history_for_key = AsyncMock()
        mock_store.append_turn = AsyncMock()
        mock_store_fn.return_value = mock_store

        await client.post("/api/v1/query", json={"query": "Stateless query here"})

    mock_store.get_history_for_key.assert_not_called()
    mock_store.append_turn.assert_not_called()


async def test_query_response_includes_cost_info(client):
    """QueryResponse must carry cost_info when the agent returns token counts."""
    from aim.schemas.query import CostInfo

    mock_response = _make_response()
    mock_response = mock_response.model_copy(update={
        "cost_info": CostInfo(
            input_tokens=1200,
            output_tokens=400,
            embedding_tokens=300,
            estimated_cost_usd=0.048,
        )
    })

    with (
        patch("aim.api.routes.query.run_reasoning_agent", AsyncMock(return_value=mock_response)),
        patch("aim.api.routes.query.get_response_cache") as mock_cache_fn,
        patch("aim.api.routes.query.get_conversation_store") as mock_store_fn,
    ):
        mock_cache = MagicMock()
        mock_cache.set_tenanted = AsyncMock()
        mock_cache_fn.return_value = mock_cache
        mock_store_fn.return_value = MagicMock()

        response = await client.post("/api/v1/query", json={"query": "Cost tracking test"})

    assert response.status_code == 200
    data = response.json()
    assert "cost_info" in data
    assert data["cost_info"]["input_tokens"] == 1200
    assert data["cost_info"]["output_tokens"] == 400
    assert data["cost_info"]["embedding_tokens"] == 300


async def test_query_allowed_in_anonymous_mode(env_vars, monkeypatch, test_app):
    """When API_KEYS is empty list, anonymous mode is active."""
    monkeypatch.setenv("API_KEYS", "[]")
    from aim.config import get_settings
    get_settings.cache_clear()

    mock_response = _make_response()

    from httpx import ASGITransport, AsyncClient

    with (
        patch(
            "aim.api.routes.query.run_reasoning_agent",
            AsyncMock(return_value=mock_response),
        ),
        patch("aim.api.routes.query.get_response_cache") as mock_cache_fn,
    ):
        mock_cache = MagicMock()
        mock_cache.set_tenanted = AsyncMock()
        mock_cache_fn.return_value = mock_cache

        async with AsyncClient(
            transport=ASGITransport(app=test_app),
            base_url="http://testserver",
        ) as anon_client:
            response = await anon_client.post(
                "/api/v1/query",
                json={"query": "Anonymous query test"},
            )

    assert response.status_code == 200
