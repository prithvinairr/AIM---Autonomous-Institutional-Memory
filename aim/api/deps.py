"""FastAPI dependencies — API key auth and distributed rate limiting.

Rate-limiting strategy
──────────────────────
Primary:  Redis sliding-window sorted-set (per API key, shared across all
          instances).  Each request adds a unique member with score = now;
          members older than the window are evicted before counting.

Fallback: In-process token bucket (per API key, per worker) — used
          automatically when Redis is unreachable.  In a multi-instance
          deployment the effective limit becomes N × rpm (one bucket per
          instance), which is documented and acceptable for degraded mode.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from collections import defaultdict
from threading import Lock
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from aim.utils.tenant_keys import tenant_id_for, tenant_key

log = structlog.get_logger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(api_key: str) -> str:
    """Derive a stable, collision-resistant ownership token from an API key.

    Uses SHA-256 (truncated to 32 hex chars = 128 bits) so ownership checks
    are immune to the prefix-collision weakness of the old 8-char approach.
    """
    return hashlib.sha256(api_key.encode()).hexdigest()[:32]


def _constant_time_key_check(candidate: str, valid_keys: list[str]) -> bool:
    """Check if candidate matches any valid key using constant-time comparison.

    Iterates all keys regardless of match to prevent timing side-channels.
    """
    matched = False
    for key in valid_keys:
        if hmac.compare_digest(candidate, key):
            matched = True
    return matched


async def verify_api_key(
    request: Request,
    api_key: str | None = Depends(_api_key_header),
) -> str:
    """Validate API key. If no keys are configured, allows anonymous access."""
    from aim.config import get_settings

    settings = get_settings()

    if not settings.api_keys:
        # Open mode — useful in dev / internal deployments
        return "anonymous"

    if not api_key or not _constant_time_key_check(api_key, settings.api_keys):
        log.warning(
            "auth.rejected",
            path=str(request.url.path),
            ip=request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Pass it as X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key


# ── In-process token-bucket fallback ─────────────────────────────────────────

class _TokenBucket:
    __slots__ = ("tokens", "last_refill", "capacity", "rate")

    def __init__(self, capacity: float, rate: float) -> None:
        self.tokens = capacity
        self.capacity = capacity
        self.rate = rate  # tokens per second
        self.last_refill = time.monotonic()

    def consume(self, tokens: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


_buckets: dict[str, _TokenBucket] = defaultdict(lambda: _TokenBucket(0, 0))
_buckets_lock = Lock()


def _get_bucket(key: str, capacity: float, rate: float) -> _TokenBucket:
    with _buckets_lock:
        if key not in _buckets or _buckets[key].capacity != capacity:
            _buckets[key] = _TokenBucket(capacity, rate)
        return _buckets[key]


def _in_process_allow(api_key: str, rpm: int) -> bool:
    bucket = _get_bucket(api_key, float(rpm), rpm / 60.0)
    return bucket.consume()


# ── Rate-limiter dependency factory ──────────────────────────────────────────

def make_rate_limiter(requests_per_minute: int = 0):
    """Returns a FastAPI dependency that enforces the configured rate limit.

    ``requests_per_minute`` is accepted for call-site documentation purposes;
    the live limit is always taken from ``settings.rate_limit_per_minute`` so
    it can be tuned at runtime via environment variable without a redeploy.

    Uses a Redis sliding-window check (distributed, accurate) when Redis is
    available, and falls back to a per-process token bucket otherwise.
    """
    async def _limiter(
        api_key: Annotated[str, Depends(verify_api_key)],
    ) -> None:
        from aim.config import get_settings
        from aim.utils.cache import get_response_cache

        rpm = get_settings().rate_limit_per_minute

        # Phase 6: tenant-prefixed shape ``aim:{tenant_id}:rl`` so rate-limit
        # buckets can never collide across tenants. The old ``aim:rl:{hash}``
        # key had a 60-second TTL (sliding-window width), so any legacy keys
        # still in Redis from before this upgrade self-retire within the
        # first minute post-deploy — no dual-read bookkeeping required.
        rl_key = tenant_key("rl", tenant_id=tenant_id_for(api_key))

        cache = get_response_cache()
        result = await cache.sliding_window_rate_limit(rl_key, rpm, window=60)

        if result is None:
            # Redis unavailable — use in-process fallback
            allowed = _in_process_allow(api_key, rpm)
            log.debug("rate_limit.fallback_inprocess", api_key_hash=hash_api_key(api_key)[:12])
        else:
            allowed = result

        if not allowed:
            log.warning(
                "rate_limit.exceeded",
                api_key_hash=hash_api_key(api_key)[:12],
                backend="redis" if result is not None else "in_process",
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {rpm} requests/minute.",
                headers={"Retry-After": "60"},
            )

    return _limiter


# ── Convenience dependencies ──────────────────────────────────────────────────

AuthDep = Annotated[str, Depends(verify_api_key)]
"""Inject the resolved API key (or 'anonymous') into a route."""

QueryRateDep = Depends(make_rate_limiter(requests_per_minute=60))
"""Apply rate limiting at query endpoints."""
