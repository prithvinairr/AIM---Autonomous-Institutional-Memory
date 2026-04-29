"""Tests for Redis cache auto-recovery and body limit middleware."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.utils.cache import ResponseCache


# ── Redis reconnection ───────────────────────────────────────────────────────

async def test_cache_reconnects_after_interval():
    """After Redis fails, cache attempts reconnection on next operation."""
    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    cache._redis = MagicMock()
    cache._redis_ok = False
    cache._last_reconnect_attempt = 0  # long ago

    # Simulate successful ping on reconnect
    cache._redis.ping = AsyncMock(return_value=True)

    await cache._try_reconnect()
    assert cache._redis_ok is True


async def test_cache_skips_reconnect_within_interval():
    """Reconnection is rate-limited to avoid hammering Redis."""
    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    cache._redis = MagicMock()
    cache._redis_ok = False
    cache._last_reconnect_attempt = time.monotonic()  # just now

    cache._redis.ping = AsyncMock(return_value=True)

    await cache._try_reconnect()
    # Should NOT have reconnected (too soon)
    assert cache._redis_ok is False
    cache._redis.ping.assert_not_awaited()


async def test_cache_reconnect_failure_stays_down():
    """If reconnect ping fails, cache stays in fallback mode."""
    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    cache._redis = MagicMock()
    cache._redis_ok = False
    cache._last_reconnect_attempt = 0

    cache._redis.ping = AsyncMock(side_effect=ConnectionError("nope"))

    await cache._try_reconnect()
    assert cache._redis_ok is False


async def test_get_triggers_reconnect_when_redis_down():
    """Cache.get() attempts reconnection when Redis is marked down."""
    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    cache._redis = MagicMock()
    cache._redis_ok = False
    cache._last_reconnect_attempt = 0

    # Reconnect succeeds
    cache._redis.ping = AsyncMock(return_value=True)
    # But no data cached
    cache._redis.get = AsyncMock(return_value=None)

    result = await cache.get("some-key")
    assert result is None
    # After reconnect, redis_ok should be True
    assert cache._redis_ok is True


async def test_rate_limiter_triggers_reconnect():
    """sliding_window_rate_limit attempts reconnect when Redis is down."""
    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    cache._redis = MagicMock()
    cache._redis_ok = False
    cache._last_reconnect_attempt = 0

    # Reconnect fails → should fall back
    cache._redis.ping = AsyncMock(side_effect=ConnectionError("nope"))

    result = await cache.sliding_window_rate_limit("test-key", 60)
    # Redis still down → returns None (fall back to in-process)
    assert result is None
