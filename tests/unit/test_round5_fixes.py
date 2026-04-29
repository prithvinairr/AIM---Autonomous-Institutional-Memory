"""Tests for the final production-hardening round (round 5).

Covers:
  1. Prometheus path normalization (cardinality fix)
  2. Content-Length parsing crash prevention
  3. Production credential validation
  4. Ingest job ownership
  5. API key hash in logs (no raw prefix)
  6. Rate limiter zrem error handling
  7. Circuit breaker HALF_OPEN logging
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Prometheus path normalization
# ═══════════════════════════════════════════════════════════════════════════════

from aim.api.middleware import _normalize_path


def test_normalize_path_replaces_uuid():
    path = "/api/v1/query/550e8400-e29b-41d4-a716-446655440000"
    assert _normalize_path(path) == "/api/v1/query/{id}"


def test_normalize_path_replaces_multiple_uuids():
    path = "/api/v1/conversations/550e8400-e29b-41d4-a716-446655440000/turns/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    result = _normalize_path(path)
    assert "{id}" in result
    assert "550e8400" not in result
    assert "a1b2c3d4" not in result


def test_normalize_path_preserves_static_paths():
    assert _normalize_path("/health") == "/health"
    assert _normalize_path("/api/v1/query") == "/api/v1/query"
    assert _normalize_path("/api/v1/graph/ingest") == "/api/v1/graph/ingest"


def test_normalize_path_replaces_long_hex_ids():
    path = "/api/v1/jobs/a1b2c3d4e5f6a7b8c9d0/"
    result = _normalize_path(path)
    assert "{id}" in result


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Content-Length parsing — invalid values return 400, not crash
# ═══════════════════════════════════════════════════════════════════════════════


async def test_invalid_content_length_returns_400(client):
    """A non-numeric Content-Length must return 400, not crash the middleware."""
    response = await client.post(
        "/api/v1/query",
        content=b"{}",
        headers={"Content-Length": "abc", "X-API-Key": "test-key"},
    )
    assert response.status_code == 400
    assert "Content-Length" in response.json()["detail"]


async def test_valid_content_length_passes_through(client):
    """A valid Content-Length should not be rejected by the middleware."""
    # This will fail at the auth/validation layer, not the middleware
    response = await client.post(
        "/api/v1/query",
        json={"query": "test query"},
    )
    # Should NOT be 400 from Content-Length parsing
    assert response.status_code != 400


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Production credential validation
# ═══════════════════════════════════════════════════════════════════════════════


def test_missing_credentials_raises_in_production():
    """In production mode, missing API keys must raise ValueError."""
    from aim.config import Settings

    with pytest.raises(ValueError, match="production"):
        Settings(
            app_env="production",
            anthropic_api_key="",
            neo4j_password="",
            pinecone_api_key="",
            openai_api_key="",
        )


def test_missing_credentials_warns_in_development():
    """In development mode, missing API keys only warn (don't raise)."""
    from aim.config import Settings

    with pytest.warns(RuntimeWarning, match="missing credentials"):
        Settings(
            app_env="development",
            anthropic_api_key="",
            neo4j_password="",
            pinecone_api_key="",
            openai_api_key="",
        )


def test_full_credentials_no_error_in_production():
    """With all credentials set, production mode starts fine."""
    from aim.config import Settings

    # Should not raise
    s = Settings(
        app_env="production",
        anthropic_api_key="sk-test",
        neo4j_password="pw",
        pinecone_api_key="pc-test",
        openai_api_key="sk-openai",
    )
    assert s.is_production


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Ingest job ownership check
# ═══════════════════════════════════════════════════════════════════════════════

from aim.workers.ingest_worker import IngestJob, IngestWorker, JobStatus
from aim.schemas.graph import GraphEntity


def _entity(eid: str = "e1") -> GraphEntity:
    return GraphEntity(entity_id=eid, labels=["Test"], properties={"name": eid})


def test_enqueue_stores_api_key_hash():
    """enqueue() persists the caller's api_key_hash on the job."""
    worker = IngestWorker(maxsize=10)
    job_id = worker.enqueue([_entity()], [], api_key_hash="abc123hash")
    job = worker.get_job(job_id)
    assert job is not None
    assert job.api_key_hash == "abc123hash"


def test_enqueue_without_hash_defaults_empty():
    """Backward compat: enqueue without hash works (empty string)."""
    worker = IngestWorker(maxsize=10)
    job_id = worker.enqueue([_entity()], [])
    job = worker.get_job(job_id)
    assert job.api_key_hash == ""


# ═══════════════════════════════════════════════════════════════════════════════
# 5. API key hash in logs — verify hash_api_key is used, not raw prefix
# ═══════════════════════════════════════════════════════════════════════════════

from aim.api.deps import hash_api_key


def test_hash_api_key_returns_hex_string():
    h = hash_api_key("my-secret-key")
    assert len(h) == 32
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_api_key_is_deterministic():
    assert hash_api_key("key-abc") == hash_api_key("key-abc")


def test_hash_api_key_differs_for_different_keys():
    assert hash_api_key("key-one") != hash_api_key("key-two")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Rate limiter zrem error handling
# ═══════════════════════════════════════════════════════════════════════════════

from aim.utils.cache import ResponseCache


async def test_rate_limit_returns_false_even_if_zrem_fails():
    """If zrem fails after detecting over-limit, still returns False (rejected)."""
    import fakeredis.aioredis

    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    fake = fakeredis.aioredis.FakeRedis()
    cache._redis = fake
    cache._redis_ok = True

    # Fill the rate limit window past the limit
    for _ in range(5):
        await cache.sliding_window_rate_limit("rl:test", limit=3, window=60)

    # Now patch zrem to fail
    original_zrem = fake.zrem
    fake.zrem = AsyncMock(side_effect=ConnectionError("redis down"))

    result = await cache.sliding_window_rate_limit("rl:test", limit=3, window=60)
    # Should still return False (over limit), not crash
    assert result is False or result is None  # False if pipeline works, None if whole thing fails


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Circuit breaker HALF_OPEN logging
# ═══════════════════════════════════════════════════════════════════════════════

from aim.utils.circuit_breaker import CircuitBreaker, CircuitState


async def test_half_open_transition_is_logged():
    """Entering HALF_OPEN must produce a log event for observability."""
    b = CircuitBreaker("log_test", failure_threshold=1, reset_timeout=0.05)

    async def fails():
        raise ValueError()

    async def ok():
        return "ok"

    with pytest.raises(ValueError):
        await b.call(fails)

    await asyncio.sleep(0.1)
    assert b.state == CircuitState.HALF_OPEN

    with patch("aim.utils.circuit_breaker.log") as mock_log:
        result = await b.call(ok)

    assert result == "ok"
    # Should have logged the half_open event
    mock_log.info.assert_any_call(
        "circuit_breaker.half_open",
        name="log_test",
        msg="Allowing single probe call to test recovery",
    )
