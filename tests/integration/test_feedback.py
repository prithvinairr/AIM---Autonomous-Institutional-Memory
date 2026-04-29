"""Integration tests for /api/v1/query/{id}/feedback routes."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from aim.schemas.provenance import ProvenanceMap
from aim.schemas.query import QueryResponse, SubQueryResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cached_response(query_id=None) -> dict:
    qid = query_id or uuid4()
    prov = ProvenanceMap(
        query_id=qid,
        sources={},
        graph_nodes=[],
        sub_query_traces=[],
        citation_map={},
        overall_confidence=0.85,
        reasoning_steps=[],
    )
    return QueryResponse(
        query_id=qid,
        original_query="test query",
        answer="test answer",
        provenance=prov,
        model_used="claude-opus-4-6",
        latency_ms=100.0,
    ).model_dump(mode="json")


# ── POST /api/v1/query/{id}/feedback ─────────────────────────────────────────

async def test_submit_feedback_returns_201(client):
    from unittest.mock import patch

    query_id = uuid4()
    cached = _cached_response(query_id)

    with patch("aim.api.routes.feedback.get_response_cache") as mock_cache_fn:
        mock_cache = MagicMock()
        mock_cache.get_tenanted = AsyncMock(return_value=cached)
        mock_cache.set_tenanted_with_ttl = AsyncMock()
        mock_cache_fn.return_value = mock_cache

        response = await client.post(
            f"/api/v1/query/{query_id}/feedback",
            json={"rating": "positive"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["rating"] == "positive"
    assert data["stored"] is True
    assert "feedback_id" in data
    assert "created_at" in data


async def test_submit_feedback_with_comment(client):
    from unittest.mock import patch

    query_id = uuid4()
    cached = _cached_response(query_id)

    with patch("aim.api.routes.feedback.get_response_cache") as mock_cache_fn:
        mock_cache = MagicMock()
        mock_cache.get_tenanted = AsyncMock(return_value=cached)
        mock_cache.set_tenanted_with_ttl = AsyncMock()
        mock_cache_fn.return_value = mock_cache

        response = await client.post(
            f"/api/v1/query/{query_id}/feedback",
            json={"rating": "negative", "comment": "The answer missed key context."},
        )

    assert response.status_code == 201


async def test_submit_feedback_404_when_query_not_cached(client):
    from unittest.mock import patch

    with patch("aim.api.routes.feedback.get_response_cache") as mock_cache_fn:
        mock_cache = MagicMock()
        mock_cache.get_tenanted = AsyncMock(return_value=None)
        mock_cache_fn.return_value = mock_cache

        response = await client.post(
            f"/api/v1/query/{uuid4()}/feedback",
            json={"rating": "positive"},
        )

    assert response.status_code == 404


async def test_submit_feedback_uses_long_ttl(client):
    """set_with_ttl must be called with feedback_ttl_seconds, not the default TTL."""
    from unittest.mock import patch
    from aim.config import get_settings

    query_id = uuid4()
    captured_ttl: list[int] = []

    async def _capture_ttl(tenant_id, key, value, ttl):
        captured_ttl.append(ttl)

    with patch("aim.api.routes.feedback.get_response_cache") as mock_cache_fn:
        mock_cache = MagicMock()
        mock_cache.get_tenanted = AsyncMock(return_value=_cached_response(query_id))
        mock_cache.set_tenanted_with_ttl = AsyncMock(side_effect=_capture_ttl)
        mock_cache_fn.return_value = mock_cache

        await client.post(
            f"/api/v1/query/{query_id}/feedback",
            json={"rating": "neutral"},
        )

    settings = get_settings()
    assert len(captured_ttl) == 1
    assert captured_ttl[0] == settings.feedback_ttl_seconds
    # Must be substantially longer than the default 1-hour query cache TTL
    assert captured_ttl[0] > settings.response_cache_ttl_seconds


async def test_submit_feedback_requires_api_key(test_app):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as anon:
        response = await anon.post(
            f"/api/v1/query/{uuid4()}/feedback",
            json={"rating": "positive"},
        )
    assert response.status_code == 401


async def test_submit_feedback_invalid_rating_returns_422(client):
    response = await client.post(
        f"/api/v1/query/{uuid4()}/feedback",
        json={"rating": "invalid_value"},
    )
    assert response.status_code == 422


# ── GET /api/v1/query/{id}/feedback ──────────────────────────────────────────

async def test_get_feedback_returns_stored_record(client):
    from unittest.mock import patch
    from aim.schemas.feedback import StoredFeedback
    from tests.conftest import TEST_API_KEY

    query_id = uuid4()
    from aim.api.deps import hash_api_key
    stored = StoredFeedback(
        feedback_id=str(uuid4()),
        query_id=str(query_id),
        rating="positive",
        comment=None,
        api_key_hash=hash_api_key(TEST_API_KEY),
        created_at=datetime.now(timezone.utc),
    )

    with patch("aim.api.routes.feedback.get_response_cache") as mock_cache_fn:
        mock_cache = MagicMock()
        mock_cache.get_tenanted = AsyncMock(return_value=stored.model_dump(mode="json"))
        mock_cache_fn.return_value = mock_cache

        response = await client.get(f"/api/v1/query/{query_id}/feedback")

    assert response.status_code == 200
    data = response.json()
    assert data["rating"] == "positive"
    assert data["query_id"] == str(query_id)


async def test_get_feedback_404_when_not_found(client):
    from unittest.mock import patch

    with patch("aim.api.routes.feedback.get_response_cache") as mock_cache_fn:
        mock_cache = MagicMock()
        mock_cache.get_tenanted = AsyncMock(return_value=None)
        mock_cache_fn.return_value = mock_cache

        response = await client.get(f"/api/v1/query/{uuid4()}/feedback")

    assert response.status_code == 404


async def test_get_feedback_403_for_different_api_key(client):
    """A caller cannot read feedback submitted by a different API key."""
    from unittest.mock import patch
    from aim.schemas.feedback import StoredFeedback

    query_id = uuid4()
    from aim.api.deps import hash_api_key
    stored = StoredFeedback(
        feedback_id=str(uuid4()),
        query_id=str(query_id),
        rating="negative",
        comment=None,
        api_key_hash=hash_api_key("different-key-xxxxxxxxx"),
        created_at=datetime.now(timezone.utc),
    )

    with patch("aim.api.routes.feedback.get_response_cache") as mock_cache_fn:
        mock_cache = MagicMock()
        mock_cache.get_tenanted = AsyncMock(return_value=stored.model_dump(mode="json"))
        mock_cache_fn.return_value = mock_cache

        response = await client.get(f"/api/v1/query/{query_id}/feedback")

    assert response.status_code == 403
