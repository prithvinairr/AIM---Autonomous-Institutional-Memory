"""Tests for the MCP ingest worker."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.workers.mcp_ingest_worker import (
    MCPIngestWorker,
    get_mcp_ingest_worker,
    reset_mcp_ingest_worker,
)


@pytest.fixture
def worker():
    """Create an MCPIngestWorker with mocked settings."""
    with patch("aim.config.get_settings") as mock_gs:
        mock_gs.return_value = MagicMock(mcp_ingest_interval_seconds=60)
        w = MCPIngestWorker()
        yield w


# ── Lifecycle ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_sets_running(worker):
    with patch.object(worker, "_run", new_callable=AsyncMock):
        await worker.start()
        assert worker._running is True
        assert worker._task is not None
        await worker.stop()


@pytest.mark.asyncio
async def test_stop_cancels_task(worker):
    with patch.object(worker, "_run", new_callable=AsyncMock):
        await worker.start()
        await worker.stop()
        assert worker._running is False


@pytest.mark.asyncio
async def test_double_start(worker):
    with patch.object(worker, "_run", new_callable=AsyncMock):
        await worker.start()
        task1 = worker._task
        await worker.start()
        assert worker._task is task1
        await worker.stop()


@pytest.mark.asyncio
async def test_stop_when_not_started(worker):
    await worker.stop()


# ── Singleton ────────────────────────────────────────────────────────────────

def test_singleton():
    with patch("aim.config.get_settings") as mock_gs:
        mock_gs.return_value = MagicMock(mcp_ingest_interval_seconds=60)
        reset_mcp_ingest_worker()
        w1 = get_mcp_ingest_worker()
        w2 = get_mcp_ingest_worker()
        assert w1 is w2
        reset_mcp_ingest_worker()


# ── Cursor helpers ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_cursor_returns_none_without_redis(worker):
    mock_cache = MagicMock()
    mock_cache._redis = None
    with patch("aim.utils.cache.get_response_cache", return_value=mock_cache):
        result = await worker._get_cursor("slack://channel/general")
        assert result is None


@pytest.mark.asyncio
async def test_set_cursor_noop_without_redis(worker):
    mock_cache = MagicMock()
    mock_cache._redis = None
    with patch("aim.utils.cache.get_response_cache", return_value=mock_cache):
        await worker._set_cursor("slack://channel/general", "12345")


# ── Poll cycle ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_poll_all_providers_handles_empty_resources(worker):
    mock_handler = MagicMock()
    mock_handler.list_resources.return_value = []
    with patch("aim.mcp.handler.MCPHandler", return_value=mock_handler):
        await worker._poll_all_providers()


@pytest.mark.asyncio
async def test_poll_handles_resource_error(worker):
    mock_resource = MagicMock()
    mock_resource.uri = "slack://channel/test"

    mock_handler = MagicMock()
    mock_handler.list_resources.return_value = [mock_resource]
    mock_handler.read_resource = AsyncMock(side_effect=RuntimeError("test error"))

    with patch("aim.mcp.handler.MCPHandler", return_value=mock_handler):
        await worker._poll_all_providers()


# ── Webhook stream ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tail_webhook_stream_noop_without_redis(worker):
    mock_cache = MagicMock()
    mock_cache._redis = None
    with patch("aim.utils.cache.get_response_cache", return_value=mock_cache):
        await worker._tail_webhook_stream()
