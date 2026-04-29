"""Phase 6 — tenant-scoped response cache.

Pre-Phase-6 the cache wrote and read keys under ``aim:{key}``. After Phase 6,
the canonical location is ``aim:{tenant_id}:{key}``. These tests pin:

* Two tenants using the same logical ``key`` never collide.
* ``get_tenanted`` dual-reads the legacy ``aim:{key}`` path when the new
  tenant-scoped key is missing — no data loss during migration.
* ``set_tenanted_with_ttl`` retires the legacy copy so pre-upgrade state
  can't zombie back through the legacy path after a fresh write.
* ``delete_tenanted`` removes both forms idempotently.
* In-memory fallback mirrors the same isolation and migration behaviour when
  Redis is unavailable.
"""
from __future__ import annotations

import fakeredis.aioredis
import orjson
import pytest

from aim.utils.cache import ResponseCache, _encrypt


@pytest.fixture
def cache() -> ResponseCache:
    c = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
    c._redis = fakeredis.aioredis.FakeRedis()
    c._redis_ok = True
    return c


class TestTenantIsolation:
    async def test_two_tenants_with_same_key_do_not_collide(self, cache):
        """If tenant A and tenant B both store under ``cache_key``, each read
        must only see their own value."""
        await cache.set_tenanted("tenant-a", "qid", {"answer": "A"})
        await cache.set_tenanted("tenant-b", "qid", {"answer": "B"})

        got_a = await cache.get_tenanted("tenant-a", "qid")
        got_b = await cache.get_tenanted("tenant-b", "qid")
        assert got_a == {"answer": "A"}
        assert got_b == {"answer": "B"}

    async def test_set_writes_to_tenant_scoped_redis_key(self, cache):
        await cache.set_tenanted("tenant-x", "qid", {"answer": "x"})
        raw = await cache._redis.get("aim:tenant-x:qid")
        assert raw is not None


class TestDualReadMigration:
    async def test_get_reads_legacy_when_new_missing(self, cache):
        """A query cached under the pre-Phase-6 key must still be retrievable
        through ``get_tenanted``."""
        # Seed legacy-only entry (with encryption applied, matching real writes)
        legacy_payload = _encrypt(orjson.dumps({"answer": "legacy"}))
        await cache._redis.setex("aim:legacy-qid", 60, legacy_payload)

        got = await cache.get_tenanted("tenant-x", "legacy-qid")
        assert got == {"answer": "legacy"}

    async def test_get_prefers_new_when_both_exist(self, cache):
        """If a fresh tenant-scoped value and a stale legacy value coexist,
        the new one wins. This matters if legacy hasn't TTL'd out yet."""
        await cache._redis.setex(
            "aim:tenant-x:qid", 60, _encrypt(orjson.dumps({"answer": "new"}))
        )
        await cache._redis.setex(
            "aim:qid", 60, _encrypt(orjson.dumps({"answer": "stale-legacy"}))
        )

        got = await cache.get_tenanted("tenant-x", "qid")
        assert got == {"answer": "new"}

    async def test_set_retires_legacy_key(self, cache):
        """After a tenanted write, the legacy copy must be gone — a later
        misconfigured reader can't dig it up."""
        await cache._redis.setex(
            "aim:qid", 60, _encrypt(orjson.dumps({"answer": "legacy"}))
        )
        await cache.set_tenanted("tenant-x", "qid", {"answer": "fresh"})

        assert await cache._redis.get("aim:qid") is None
        assert await cache._redis.get("aim:tenant-x:qid") is not None

    async def test_set_legacy_retirement_is_idempotent_when_absent(self, cache):
        """Retiring legacy when no legacy exists must not fail."""
        await cache.set_tenanted("tenant-x", "qid", {"answer": "fresh"})
        got = await cache.get_tenanted("tenant-x", "qid")
        assert got == {"answer": "fresh"}


class TestDeleteTenanted:
    async def test_delete_removes_both_forms(self, cache):
        await cache._redis.setex(
            "aim:tenant-x:qid", 60, _encrypt(orjson.dumps({"answer": "n"}))
        )
        await cache._redis.setex(
            "aim:qid", 60, _encrypt(orjson.dumps({"answer": "l"}))
        )

        await cache.delete_tenanted("tenant-x", "qid")
        assert await cache._redis.get("aim:tenant-x:qid") is None
        assert await cache._redis.get("aim:qid") is None

    async def test_delete_missing_is_noop(self, cache):
        """Deleting non-existent entries must not raise."""
        await cache.delete_tenanted("tenant-x", "never-existed")


class TestMemoryFallbackTenant:
    async def test_fallback_isolates_tenants(self):
        """When Redis is unavailable the in-memory LRU must still namespace
        by tenant."""
        cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
        cache._redis = None
        cache._redis_ok = False

        await cache.set_tenanted("tenant-a", "qid", {"answer": "A"})
        await cache.set_tenanted("tenant-b", "qid", {"answer": "B"})

        got_a = await cache.get_tenanted("tenant-a", "qid")
        got_b = await cache.get_tenanted("tenant-b", "qid")
        assert got_a == {"answer": "A"}
        assert got_b == {"answer": "B"}

    async def test_fallback_reads_legacy_lru_entry(self):
        """A pre-Phase-6 LRU entry (stored under the bare logical key) must
        still be retrievable via the tenanted path."""
        cache = ResponseCache(redis_url="redis://localhost:6379", ttl=60, maxsize=10)
        cache._redis = None
        cache._redis_ok = False

        cache._fallback.set("legacy-qid", orjson.dumps({"answer": "legacy"}))
        got = await cache.get_tenanted("tenant-x", "legacy-qid")
        assert got == {"answer": "legacy"}


class TestSetWithCustomTTL:
    async def test_custom_ttl_is_applied(self, cache):
        """``set_tenanted_with_ttl`` must honour the caller's TTL — matters
        for the feedback route which uses a 90-day TTL, not the default."""
        await cache.set_tenanted_with_ttl("tenant-x", "qid", {"v": 1}, ttl=7)
        ttl = await cache._redis.ttl("aim:tenant-x:qid")
        assert 0 < ttl <= 7
