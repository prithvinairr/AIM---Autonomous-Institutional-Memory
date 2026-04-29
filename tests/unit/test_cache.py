"""Unit tests for ResponseCache and its in-memory LRU fallback."""
from __future__ import annotations

import time

import orjson
from aim.utils.cache import ResponseCache, _MemoryLRU


# ── _MemoryLRU ────────────────────────────────────────────────────────────────

def test_memory_lru_stores_and_retrieves():
    cache = _MemoryLRU(maxsize=10, ttl=60)
    data = orjson.dumps({"answer": 42})
    cache.set("k1", data)
    assert cache.get("k1") == data


def test_memory_lru_returns_none_for_missing_key():
    cache = _MemoryLRU(maxsize=10, ttl=60)
    assert cache.get("no_such_key") is None


def test_memory_lru_evicts_oldest_entry_on_overflow():
    cache = _MemoryLRU(maxsize=2, ttl=60)
    cache.set("a", orjson.dumps(1))
    cache.set("b", orjson.dumps(2))
    cache.set("c", orjson.dumps(3))  # "a" (LRU) should be evicted
    assert cache.get("a") is None
    assert cache.get("b") is not None
    assert cache.get("c") is not None


def test_memory_lru_never_exceeds_maxsize():
    cache = _MemoryLRU(maxsize=3, ttl=60)
    for i in range(10):
        cache.set(f"k{i}", orjson.dumps(i))
    assert cache.size() <= 3


def test_memory_lru_expired_entry_returns_none():
    cache = _MemoryLRU(maxsize=10, ttl=1)
    cache.set("expiring", orjson.dumps("value"))
    # Backdate the stored timestamp to simulate expiry
    with cache._lock:
        val, _, entry_ttl = cache._store["expiring"]
        cache._store["expiring"] = (val, time.monotonic() - 2, entry_ttl)
    assert cache.get("expiring") is None


def test_memory_lru_purge_expired_removes_stale_entries():
    cache = _MemoryLRU(maxsize=10, ttl=1)
    cache.set("x", orjson.dumps("x"))
    cache.set("y", orjson.dumps("y"))
    # Backdate both entries
    with cache._lock:
        for k in list(cache._store.keys()):
            val, _, entry_ttl = cache._store[k]
            cache._store[k] = (val, time.monotonic() - 2, entry_ttl)
    removed = cache.purge_expired()
    assert removed == 2
    assert cache.size() == 0


def test_memory_lru_purge_leaves_fresh_entries_intact():
    cache = _MemoryLRU(maxsize=10, ttl=60)
    cache.set("fresh", orjson.dumps("fresh_val"))
    removed = cache.purge_expired()
    assert removed == 0
    assert cache.get("fresh") is not None


def test_memory_lru_delete_removes_entry():
    cache = _MemoryLRU(maxsize=10, ttl=60)
    cache.set("to_del", orjson.dumps(1))
    cache.delete("to_del")
    assert cache.get("to_del") is None


def test_memory_lru_delete_nonexistent_is_safe():
    cache = _MemoryLRU(maxsize=10, ttl=60)
    cache.delete("never_existed")  # should not raise


# ── ResponseCache — memory backend ───────────────────────────────────────────

async def test_response_cache_falls_back_to_memory_on_bad_redis_url():
    cache = ResponseCache(redis_url="redis://invalid-host:6379", ttl=60, maxsize=10)
    await cache.connect()
    assert cache.backend() == "memory"


async def test_response_cache_get_set_round_trip_memory():
    cache = ResponseCache(redis_url="redis://invalid-host:6379", ttl=60, maxsize=10)
    await cache.connect()
    await cache.set("q1", {"answer": "hello"})
    result = await cache.get("q1")
    assert result == {"answer": "hello"}


async def test_response_cache_get_returns_none_for_missing_key():
    cache = ResponseCache(redis_url="redis://invalid-host:6379", ttl=60, maxsize=10)
    await cache.connect()
    assert await cache.get("nonexistent-key") is None


async def test_response_cache_health_check_false_without_redis():
    cache = ResponseCache(redis_url="redis://invalid-host:6379", ttl=60, maxsize=10)
    await cache.connect()
    assert await cache.health_check() is False


async def test_response_cache_purge_expired_delegates_to_fallback():
    cache = ResponseCache(redis_url="redis://invalid-host:6379", ttl=1, maxsize=10)
    await cache.connect()
    cache._fallback.set("old_key", orjson.dumps({"v": 1}))
    with cache._fallback._lock:
        val, _, entry_ttl = cache._fallback._store["old_key"]
        cache._fallback._store["old_key"] = (val, time.monotonic() - 2, entry_ttl)
    removed = await cache.purge_expired_fallback()
    assert removed == 1


# ── ResponseCache — Redis backend via fakeredis ───────────────────────────────

async def test_response_cache_uses_redis_when_injected():
    import fakeredis.aioredis

    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    cache._redis = fakeredis.aioredis.FakeRedis()
    cache._redis_ok = True

    await cache.set("redis_key", {"data": "from redis"})
    result = await cache.get("redis_key")
    assert result == {"data": "from redis"}
    assert cache.backend() == "redis"


async def test_response_cache_health_check_true_with_fakeredis():
    import fakeredis.aioredis

    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    cache._redis = fakeredis.aioredis.FakeRedis()
    cache._redis_ok = True
    assert await cache.health_check() is True


async def test_response_cache_falls_back_to_memory_on_redis_get_error():
    """If Redis raises mid-request, the cache transparently falls back."""
    import fakeredis.aioredis
    from unittest.mock import AsyncMock

    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    # Inject a Redis that raises on GET
    fake = fakeredis.aioredis.FakeRedis()
    fake.get = AsyncMock(side_effect=ConnectionError("boom"))
    cache._redis = fake
    cache._redis_ok = True

    # Pre-populate the in-memory fallback
    cache._fallback.set("k", orjson.dumps({"v": "fallback"}))

    result = await cache.get("k")
    assert result == {"v": "fallback"}
    # Circuit should have tripped to memory after the error
    assert cache._redis_ok is False


# ── set_with_ttl ──────────────────────────────────────────────────────────────

async def test_set_with_ttl_uses_explicit_ttl_in_memory_fallback():
    """set_with_ttl stores data and is retrievable, even with the in-memory backend."""
    cache = ResponseCache(redis_url="redis://invalid-host:6379", ttl=60, maxsize=10)
    await cache.connect()
    await cache.set_with_ttl("feedback_key", {"rating": "positive"}, ttl=7_776_000)
    result = await cache.get("feedback_key")
    assert result == {"rating": "positive"}


async def test_set_delegates_to_set_with_ttl():
    """set() must behave identically to set_with_ttl(key, value, default_ttl)."""
    cache = ResponseCache(redis_url="redis://invalid-host:6379", ttl=60, maxsize=10)
    await cache.connect()
    await cache.set("plain_key", {"v": 1})
    result = await cache.get("plain_key")
    assert result == {"v": 1}


async def test_set_with_ttl_uses_explicit_ttl_in_redis():
    """set_with_ttl passes the correct TTL to Redis SETEX, not the default TTL."""
    import fakeredis.aioredis

    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    fake = fakeredis.aioredis.FakeRedis()
    cache._redis = fake
    cache._redis_ok = True

    long_ttl = 7_776_000
    await cache.set_with_ttl("fbk", {"r": "negative"}, ttl=long_ttl)

    # Verify via TTL inspection on the raw Redis key
    remaining = await fake.ttl("aim:fbk")
    # Allow ±5 s of clock drift
    assert long_ttl - 5 <= remaining <= long_ttl

    result = await cache.get("fbk")
    assert result == {"r": "negative"}


# ── _MemoryLRU.set() — update existing key (line 45) ────────────────────────

def test_memory_lru_set_existing_key_moves_to_end():
    """Setting an already-existing key moves it to MRU position (not evicted first)."""
    cache = _MemoryLRU(maxsize=3, ttl=60)
    cache.set("a", orjson.dumps(1))
    cache.set("b", orjson.dumps(2))
    cache.set("c", orjson.dumps(3))

    # Re-set "a" — should move it to end (MRU), so "b" becomes LRU
    cache.set("a", orjson.dumps(100))

    # Now add "d" — "b" (LRU) should be evicted, NOT "a"
    cache.set("d", orjson.dumps(4))
    assert cache.get("a") is not None  # moved to end, survives
    assert cache.get("b") is None  # was LRU, evicted
    assert cache.get("c") is not None
    assert cache.get("d") is not None
    # Verify the value was actually updated
    assert orjson.loads(cache.get("a")) == 100


# ── ResponseCache.connect() — successful Redis ping (lines 105-106) ─────────

async def test_response_cache_connect_success_with_fakeredis():
    """connect() sets _redis_ok=True when Redis ping succeeds."""
    import fakeredis.aioredis
    from unittest.mock import AsyncMock, patch

    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    fake = fakeredis.aioredis.FakeRedis()
    with patch("redis.asyncio.from_url", AsyncMock(return_value=fake)):
        await cache.connect()
    assert cache._redis_ok is True
    assert cache._redis is fake
    assert cache.backend() == "redis"


# ── ResponseCache.set() — Redis exception handling (lines 152-154) ──────────

async def test_response_cache_set_falls_back_on_redis_error():
    """If Redis raises during set(), cache flips to memory and stores in fallback."""
    import fakeredis.aioredis
    from unittest.mock import AsyncMock

    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    fake = fakeredis.aioredis.FakeRedis()
    fake.setex = AsyncMock(side_effect=ConnectionError("write failed"))
    cache._redis = fake
    cache._redis_ok = True

    await cache.set("fail_key", {"v": "data"})

    # Circuit should have tripped
    assert cache._redis_ok is False
    # Value should be in the in-memory fallback
    result = await cache.get("fail_key")
    assert result == {"v": "data"}


# ── ResponseCache.delete() (lines 159-164) ──────────────────────────────────

async def test_response_cache_delete_removes_from_redis_and_fallback():
    """delete() removes the key from both Redis and the in-memory fallback."""
    import fakeredis.aioredis

    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    fake = fakeredis.aioredis.FakeRedis()
    cache._redis = fake
    cache._redis_ok = True

    await cache.set("del_me", {"v": 1})
    await cache.delete("del_me")
    assert await cache.get("del_me") is None


async def test_response_cache_delete_ignores_redis_error():
    """delete() swallows Redis errors and still deletes from fallback."""
    import fakeredis.aioredis
    from unittest.mock import AsyncMock

    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    fake = fakeredis.aioredis.FakeRedis()
    fake.delete = AsyncMock(side_effect=ConnectionError("boom"))
    cache._redis = fake
    cache._redis_ok = True

    # Put something in fallback directly
    cache._fallback.set("del_me", orjson.dumps({"v": 1}))
    await cache.delete("del_me")
    assert cache._fallback.get("del_me") is None


# ── ResponseCache.close() (lines 167-168) ───────────────────────────────────

async def test_response_cache_close_calls_aclose():
    """close() calls aclose() on the Redis client."""
    from unittest.mock import AsyncMock

    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    mock_redis = AsyncMock()
    cache._redis = mock_redis
    await cache.close()
    mock_redis.aclose.assert_called_once()


# ── ResponseCache.health_check() — exception path (lines 175-176) ───────────

async def test_response_cache_health_check_exception_flips_redis_ok():
    """health_check() sets _redis_ok=False when ping raises."""
    from unittest.mock import AsyncMock

    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=ConnectionError("ping failed"))
    cache._redis = mock_redis
    cache._redis_ok = True

    result = await cache.health_check()
    assert result is False
    assert cache._redis_ok is False


# ── ResponseCache.sliding_window_rate_limit() — exception (lines 228-230) ───

async def test_rate_limit_returns_none_on_pipeline_exception():
    """sliding_window_rate_limit returns None when the pipeline raises."""
    from unittest.mock import AsyncMock, MagicMock

    cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    mock_redis = AsyncMock()
    mock_redis.pipeline = MagicMock(side_effect=ConnectionError("pipeline error"))
    cache._redis = mock_redis
    cache._redis_ok = True

    result = await cache.sliding_window_rate_limit("aim:rl:test", limit=10, window=60)
    assert result is None
