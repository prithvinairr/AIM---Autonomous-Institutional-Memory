"""Tests for aim.utils.audit_log — external API audit logging."""
from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.utils.audit_log import (
    AuditEntry,
    AuditLogger,
    get_audit_logger,
    reset_audit_logger,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_audit_logger()
    yield
    reset_audit_logger()


# ── AuditEntry ───────────────────────────────────────────────────────────────

class TestAuditEntry:
    def test_creates_with_timestamp(self):
        before = time.time()
        entry = AuditEntry(
            query_id="q-123",
            provider="anthropic",
            model="claude-3",
            endpoint_type="llm_inference",
            data_summary={"graph_entities": 5},
        )
        after = time.time()
        assert before <= entry.timestamp <= after
        assert entry.direction == "outbound"
        assert entry.query_id == "q-123"

    def test_to_dict(self):
        entry = AuditEntry(
            query_id="q-123",
            provider="openai",
            model="gpt-4",
            endpoint_type="embedding",
            data_summary={"num_texts": 3, "total_chars": 1500},
            classifications_sent=["INTERNAL"],
        )
        d = entry.to_dict()
        assert d["provider"] == "openai"
        assert d["model"] == "gpt-4"
        assert d["endpoint_type"] == "embedding"
        assert d["data_summary"]["num_texts"] == 3
        assert d["classifications_sent"] == ["INTERNAL"]
        assert "timestamp" in d

    def test_default_empty_classifications(self):
        entry = AuditEntry(
            query_id="q-1",
            provider="p",
            model="m",
            endpoint_type="e",
            data_summary={},
        )
        assert entry.classifications_sent == []


# ── AuditLogger ──────────────────────────────────────────────────────────────

class TestAuditLogger:
    @pytest.fixture
    def logger(self):
        al = AuditLogger()
        al._enabled = True
        al._ttl = 3600
        return al

    @pytest.mark.asyncio
    async def test_log_llm_call_with_redis(self, logger):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.zadd = AsyncMock()
        mock_redis.zremrangebyscore = AsyncMock()
        logger._redis = mock_redis

        await logger.log_llm_call(
            query_id="q-1",
            provider="anthropic",
            model="claude-3",
            num_entities=10,
            num_snippets=5,
            num_mcp_items=3,
            classifications_sent=["INTERNAL", "CONFIDENTIAL"],
            estimated_input_tokens=2000,
        )

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 3600  # TTL
        stored_data = json.loads(call_args[0][2])
        assert stored_data["provider"] == "anthropic"
        assert stored_data["data_summary"]["graph_entities"] == 10
        assert stored_data["data_summary"]["vector_snippets"] == 5
        assert stored_data["endpoint_type"] == "llm_inference"

    @pytest.mark.asyncio
    async def test_log_embedding_call_with_redis(self, logger):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.zadd = AsyncMock()
        mock_redis.zremrangebyscore = AsyncMock()
        logger._redis = mock_redis

        await logger.log_embedding_call(
            query_id="q-2",
            provider="openai",
            model="text-embedding-3-small",
            num_texts=8,
            total_chars=5000,
        )

        mock_redis.setex.assert_called_once()
        stored_data = json.loads(mock_redis.setex.call_args[0][2])
        assert stored_data["endpoint_type"] == "embedding"
        assert stored_data["data_summary"]["num_texts"] == 8

    @pytest.mark.asyncio
    async def test_disabled_logger_skips_storage(self, logger):
        logger._enabled = False
        mock_redis = AsyncMock()
        logger._redis = mock_redis

        await logger.log_llm_call(
            query_id="q-3",
            provider="anthropic",
            model="claude-3",
        )

        mock_redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_when_redis_unavailable(self, logger):
        logger._redis = None
        # Should not raise, just log via structlog
        await logger.log_llm_call(
            query_id="q-4",
            provider="anthropic",
            model="claude-3",
        )

    @pytest.mark.asyncio
    async def test_redis_error_handled_gracefully(self, logger):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=ConnectionError("Redis down"))
        logger._redis = mock_redis

        # Should not raise
        await logger.log_llm_call(
            query_id="q-5",
            provider="anthropic",
            model="claude-3",
        )

    @pytest.mark.asyncio
    async def test_get_recent_empty(self, logger):
        mock_redis = AsyncMock()
        mock_redis.zrevrange = AsyncMock(return_value=[])
        logger._redis = mock_redis

        result = await logger.get_recent(limit=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_recent_with_entries(self, logger):
        entry_data = json.dumps({
            "timestamp": time.time(),
            "query_id": "q-1",
            "provider": "anthropic",
            "model": "claude-3",
            "endpoint_type": "llm_inference",
            "direction": "outbound",
            "data_summary": {},
            "classifications_sent": [],
        })
        mock_redis = AsyncMock()
        mock_redis.zrevrange = AsyncMock(return_value=["key1", "key2"])
        mock_redis.get = AsyncMock(return_value=entry_data)
        logger._redis = mock_redis

        result = await logger.get_recent(limit=5)
        assert len(result) == 2
        assert result[0]["provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_get_recent_no_redis(self, logger):
        logger._redis = None
        result = await logger.get_recent()
        assert result == []

    @pytest.mark.asyncio
    async def test_index_trimming(self, logger):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.zadd = AsyncMock()
        mock_redis.zremrangebyscore = AsyncMock()
        logger._redis = mock_redis

        await logger.log_llm_call(query_id="q-1", provider="p", model="m")

        # Verify zremrangebyscore was called to trim old entries
        mock_redis.zremrangebyscore.assert_called_once()


# ── Singleton ────────────────────────────────────────────────────────────────

class TestSingleton:
    def test_returns_same_instance(self):
        a = get_audit_logger()
        b = get_audit_logger()
        assert a is b

    def test_reset_creates_new_instance(self):
        a = get_audit_logger()
        reset_audit_logger()
        b = get_audit_logger()
        assert a is not b
