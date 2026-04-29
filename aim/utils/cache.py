"""Response cache — Redis primary, thread-safe in-memory fallback.

In production set REDIS_URL to a real Redis instance.
If Redis is unreachable, automatically falls back to a bounded in-memory LRU
so the service stays alive (degraded but functional).

When ``cache_encryption_enabled=True``, cached values are encrypted at rest
with the Fernet key from ``encryption_key``.  This prevents PII that was
properly redacted from the LLM context from being readable in plaintext
if the Redis instance is compromised.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

import orjson
import structlog

log = structlog.get_logger(__name__)


# ── At-rest encryption helpers ───────────────────────────────────────────────

# Module-level Fernet instance cache — keyed by encryption_key to handle rotation.
_fernet_cache: dict[str, Any] = {}

def _get_fernet():
    """Return a cached Fernet cipher if encryption is configured, else None."""
    try:
        from aim.config import get_settings
        settings = get_settings()
        if not settings.cache_encryption_enabled or not settings.encryption_key:
            return None
        key = settings.encryption_key
        if key not in _fernet_cache:
            from cryptography.fernet import Fernet
            _fernet_cache[key] = Fernet(key.encode())
        return _fernet_cache[key]
    except Exception:
        return None


def _encrypt(data: bytes) -> bytes:
    """Encrypt data if Fernet is available, else passthrough."""
    f = _get_fernet()
    return f.encrypt(data) if f else data


def _decrypt(data: bytes) -> bytes:
    """Decrypt data if Fernet is available, else passthrough."""
    f = _get_fernet()
    if f is None:
        return data
    try:
        return f.decrypt(data)
    except Exception:
        return data


# ── In-memory fallback ────────────────────────────────────────────────────────

class _MemoryLRU:
    """Thread-safe LRU cache with per-entry TTL and background reaping."""

    def __init__(self, maxsize: int, ttl: int) -> None:
        self._store: OrderedDict[str, tuple[bytes, float, int]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> bytes | None:
        with self._lock:
            if key not in self._store:
                return None
            value, ts, entry_ttl = self._store[key]
            if time.monotonic() - ts > entry_ttl:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, time.monotonic(), ttl if ttl is not None else self._ttl)
            while len(self._store) > self._maxsize:
                self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def purge_expired(self) -> int:
        now = time.monotonic()
        removed = 0
        with self._lock:
            expired = [
                k for k, (_, ts, entry_ttl) in self._store.items()
                if now - ts > entry_ttl
            ]
            for k in expired:
                del self._store[k]
                removed += 1
        return removed


# ── Redis-backed cache ────────────────────────────────────────────────────────

class ResponseCache:
    """Unified cache interface — tries Redis, falls back to in-memory.

    When Redis becomes unreachable, ``_redis_ok`` flips to ``False`` and all
    operations transparently fall back to the in-memory LRU.  A background
    reconnection attempt fires every ``_RECONNECT_INTERVAL`` seconds so the
    cache can self-heal without a process restart.
    """

    _RECONNECT_INTERVAL: float = 30.0  # seconds between reconnect attempts

    def __init__(self, redis_url: str, ttl: int, maxsize: int) -> None:
        self._ttl = ttl
        self._fallback = _MemoryLRU(maxsize=maxsize, ttl=ttl)
        self._redis: Any = None
        self._redis_url = redis_url
        self._redis_ok = False
        self._last_reconnect_attempt: float = 0.0

    async def connect(self) -> None:
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            self._redis = await aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=False,
                socket_connect_timeout=3,
                socket_timeout=2,
            )
            await self._redis.ping()
            self._redis_ok = True
            log.info("cache.redis_connected", url=self._redis_url)
        except Exception as exc:
            log.warning("cache.redis_unavailable_fallback", error=str(exc))
            self._redis_ok = False

    async def _try_reconnect(self) -> None:
        """Attempt to reconnect to Redis if enough time has passed since the last try."""
        now = time.monotonic()
        if now - self._last_reconnect_attempt < self._RECONNECT_INTERVAL:
            return
        self._last_reconnect_attempt = now
        try:
            if self._redis:
                await self._redis.ping()
                self._redis_ok = True
                log.info("cache.redis_reconnected")
        except Exception:
            pass  # still down — will retry next interval

    async def get(self, key: str) -> dict[str, Any] | None:
        if not self._redis_ok and self._redis:
            await self._try_reconnect()
        if self._redis_ok and self._redis:
            try:
                raw = await self._redis.get(f"aim:{key}")
                if raw is not None:
                    return orjson.loads(_decrypt(raw))
            except Exception as exc:
                log.warning("cache.redis_get_failed", key=key, error=str(exc))
                self._redis_ok = False  # circuit to in-memory

        raw = self._fallback.get(key)
        return orjson.loads(raw) if raw is not None else None

    async def set(self, key: str, value: dict[str, Any]) -> None:
        await self.set_with_ttl(key, value, self._ttl)

    async def set_with_ttl(self, key: str, value: dict[str, Any], ttl: int) -> None:
        """Store a value with an explicit TTL (seconds) instead of the default."""
        encoded = _encrypt(orjson.dumps(value))
        if not self._redis_ok and self._redis:
            await self._try_reconnect()
        if self._redis_ok and self._redis:
            try:
                await self._redis.setex(f"aim:{key}", ttl, encoded)
                return
            except Exception as exc:
                log.warning("cache.redis_set_failed", key=key, error=str(exc))
                self._redis_ok = False

        self._fallback.set(key, encoded, ttl=ttl)

    async def delete(self, key: str) -> None:
        if self._redis_ok and self._redis:
            try:
                await self._redis.delete(f"aim:{key}")
            except Exception:
                pass
        self._fallback.delete(key)

    # ── Phase 6: tenant-scoped variants ──────────────────────────────────────
    #
    # Values stored through these methods live under ``aim:{tenant_id}:{key}``
    # so two tenants asking the same question can never collide in the cache
    # even when the logical ``key`` is identical (common for query hashes).
    #
    # Reads dual-read the legacy ``aim:{key}`` location so state written by
    # pre-Phase-6 code is still reachable during migration; writes / deletes
    # proactively retire the legacy key to prevent stale zombies from
    # resurfacing through the fallback path.

    def _tenanted_redis_key(self, tenant_id: str, key: str) -> str:
        return f"aim:{tenant_id}:{key}"

    def _legacy_redis_key(self, key: str) -> str:
        return f"aim:{key}"

    def _tenanted_fallback_key(self, tenant_id: str, key: str) -> str:
        # In-memory LRU is per-process already, but namespacing by tenant is
        # cheap insurance against future changes to the fallback backend.
        return f"{tenant_id}:{key}"

    async def get_tenanted(self, tenant_id: str, key: str) -> dict[str, Any] | None:
        if not self._redis_ok and self._redis:
            await self._try_reconnect()
        if self._redis_ok and self._redis:
            try:
                raw = await self._redis.get(self._tenanted_redis_key(tenant_id, key))
                if raw is None:
                    # Phase 6 dual-read fallback to pre-upgrade location.
                    raw = await self._redis.get(self._legacy_redis_key(key))
                if raw is not None:
                    return orjson.loads(_decrypt(raw))
            except Exception as exc:
                log.warning("cache.redis_get_failed", key=key, error=str(exc))
                self._redis_ok = False

        raw = self._fallback.get(self._tenanted_fallback_key(tenant_id, key))
        if raw is None:
            # Fallback legacy probe — pre-Phase-6 LRU entries live under the
            # plain logical key.
            raw = self._fallback.get(key)
        return orjson.loads(raw) if raw is not None else None

    async def set_tenanted(
        self, tenant_id: str, key: str, value: dict[str, Any]
    ) -> None:
        await self.set_tenanted_with_ttl(tenant_id, key, value, self._ttl)

    async def set_tenanted_with_ttl(
        self, tenant_id: str, key: str, value: dict[str, Any], ttl: int
    ) -> None:
        encoded = _encrypt(orjson.dumps(value))
        if not self._redis_ok and self._redis:
            await self._try_reconnect()
        if self._redis_ok and self._redis:
            try:
                tenanted = self._tenanted_redis_key(tenant_id, key)
                await self._redis.setex(tenanted, ttl, encoded)
                # Retire legacy — idempotent.
                try:
                    await self._redis.delete(self._legacy_redis_key(key))
                except Exception:
                    pass  # legacy retirement is best-effort
                return
            except Exception as exc:
                log.warning("cache.redis_set_failed", key=key, error=str(exc))
                self._redis_ok = False

        self._fallback.set(
            self._tenanted_fallback_key(tenant_id, key), encoded, ttl=ttl
        )
        # Retire fallback legacy copy, too.
        self._fallback.delete(key)

    async def delete_tenanted(self, tenant_id: str, key: str) -> None:
        if self._redis_ok and self._redis:
            try:
                await self._redis.delete(
                    self._tenanted_redis_key(tenant_id, key),
                    self._legacy_redis_key(key),
                )
            except Exception:
                pass
        self._fallback.delete(self._tenanted_fallback_key(tenant_id, key))
        self._fallback.delete(key)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    async def health_check(self) -> bool:
        if self._redis_ok and self._redis:
            try:
                await self._redis.ping()
                return True
            except Exception:
                self._redis_ok = False
        return False

    def backend(self) -> str:
        return "redis" if self._redis_ok else "memory"

    async def sliding_window_rate_limit(
        self, key: str, limit: int, window: int = 60
    ) -> bool | None:
        """Distributed sliding-window rate limit using a Redis sorted set.

        Returns:
          ``True``   — request is allowed (count ≤ limit).
          ``False``  — request is rejected (count > limit).
          ``None``   — Redis unavailable; caller should fall back to an
                       in-process check.

        Algorithm:
          1. Remove members with score < (now - window)  → evict old requests.
          2. Add a unique member with score = now         → record this request.
          3. Count remaining members                     → total in window.
          4. If count > limit, remove the member we just added and return False.
          5. Set key TTL = window + 1s to auto-expire idle keys.

        All four writes are pipelined in one round-trip.  The reject-undo in
        step 4 is a separate call but is only reached on rate-limit events
        (rare) and does not require atomicity with the pipeline.
        """
        if not self._redis_ok and self._redis:
            await self._try_reconnect()
        if not self._redis_ok or not self._redis:
            return None

        import uuid as _uuid
        now = time.time()
        member = str(_uuid.uuid4())
        try:
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(key, "-inf", now - window)
            pipe.zadd(key, {member: now})
            pipe.zcard(key)
            pipe.expire(key, window + 1)
            results = await pipe.execute()
            count = int(results[2])

            if count > limit:
                try:
                    await self._redis.zrem(key, member)
                except Exception:
                    pass  # member stays — minor over-count on next window
                return False
            return True
        except Exception as exc:
            log.warning("cache.rate_limit_error", key=key, error=str(exc))
            return None  # fall back to in-process

    async def purge_expired_fallback(self) -> int:
        """Periodic maintenance — call from a background task."""
        return self._fallback.purge_expired()


# ── Singleton ─────────────────────────────────────────────────────────────────

_cache_instance: ResponseCache | None = None


def get_response_cache() -> ResponseCache:
    global _cache_instance
    if _cache_instance is None:
        from aim.config import get_settings

        s = get_settings()
        _cache_instance = ResponseCache(
            redis_url=s.redis_url,
            ttl=s.response_cache_ttl_seconds,
            maxsize=s.response_cache_max_size,
        )
    return _cache_instance
