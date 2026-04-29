"""Phase 6 — dual-read migration for the user_threads index.

Before Phase 6 the index lived at ``aim:user_threads:{hash}``. After Phase 6
the canonical location is ``aim:{tenant_id}:user_threads`` (the tenant_id is
the same hash). These tests pin:

* A caller whose index only exists at the legacy location still sees their
  threads via ``list_threads`` (fallback read works).
* The first post-upgrade write folds the legacy index into the new location
  and deletes the legacy key (zombies don't resurface via fallback).
* ``delete_thread`` retires the legacy key too — a delete after the upgrade
  can't leave the thread visible via legacy fallback.
* Pure-new-form data (no legacy key present) works exactly like before.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import fakeredis.aioredis
import orjson
import pytest

from aim.schemas.conversation import ConversationTurn
from aim.utils.conversation_store import ConversationStore


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(fake_redis) -> ConversationStore:
    s = ConversationStore(redis_url="redis://localhost:6379", ttl_seconds=3600, max_turns=5)
    s._redis = fake_redis
    s._ok = True
    return s


def _turn(q: str = "What?") -> ConversationTurn:
    return ConversationTurn(
        query_id=uuid4(),
        user_message=q,
        assistant_message="A.",
        reasoning_depth="standard",
        latency_ms=100.0,
        confidence=0.9,
        source_count=1,
    )


def _seed_legacy_index(fake_redis, api_key: str, entries: list[dict]) -> str:
    """Seed the pre-Phase-6 index key verbatim and return its name."""
    import hashlib

    h = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    legacy_name = f"aim:user_threads:{h}"

    import asyncio

    async def _seed():
        await fake_redis.setex(legacy_name, 3600, orjson.dumps(entries))

    asyncio.get_event_loop().run_until_complete(_seed())
    return legacy_name


class TestListThreadsFallback:
    async def test_reads_from_legacy_when_new_is_empty(self, store, fake_redis):
        api_key = "legacy-user-1"
        tid = str(uuid4())
        legacy_entry = {
            "thread_id": tid,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_query": "legacy q",
            "turn_count": 3,
        }
        import hashlib

        h = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        await fake_redis.setex(
            f"aim:user_threads:{h}", 3600, orjson.dumps([legacy_entry])
        )

        summaries = await store.list_threads(api_key)
        assert len(summaries) == 1
        assert str(summaries[0].thread_id) == tid
        assert summaries[0].last_query == "legacy q"

    async def test_prefers_new_when_both_exist(self, store, fake_redis):
        """If NEW has data, it wins — legacy is not read. This matters when
        the new write happened but legacy hasn't TTL'd yet."""
        api_key = "mixed-user"
        new_tid = str(uuid4())
        legacy_tid = str(uuid4())

        def entry(tid: str, q: str) -> dict:
            ts = datetime.now(timezone.utc).isoformat()
            return {
                "thread_id": tid,
                "updated_at": ts,
                "created_at": ts,
                "last_query": q,
                "turn_count": 1,
            }

        # Seed both
        import hashlib

        tenant = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        await fake_redis.setex(
            f"aim:{tenant}:user_threads", 3600, orjson.dumps([entry(new_tid, "new")])
        )
        await fake_redis.setex(
            f"aim:user_threads:{tenant}",
            3600,
            orjson.dumps([entry(legacy_tid, "legacy")]),
        )

        summaries = await store.list_threads(api_key)
        assert len(summaries) == 1
        assert str(summaries[0].thread_id) == new_tid


class TestWriteMigratesLegacy:
    async def test_first_write_folds_legacy_into_new(self, store, fake_redis):
        api_key = "migrating-user"
        legacy_tid = str(uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        legacy_entry = {
            "thread_id": legacy_tid,
            "updated_at": ts,
            "created_at": ts,
            "last_query": "from legacy",
            "turn_count": 2,
        }
        import hashlib

        tenant = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        legacy_name = f"aim:user_threads:{tenant}"
        new_name = f"aim:{tenant}:user_threads"
        await fake_redis.setex(legacy_name, 3600, orjson.dumps([legacy_entry]))

        # Perform a new write via append_turn — triggers _update_index.
        new_tid = uuid4()
        await store.append_turn(new_tid, api_key, _turn("fresh"))

        # Legacy must be deleted.
        assert await fake_redis.get(legacy_name) is None

        # NEW must contain both the legacy thread AND the fresh one.
        raw = await fake_redis.get(new_name)
        assert raw is not None
        index = orjson.loads(raw)
        thread_ids = {e["thread_id"] for e in index}
        assert str(new_tid) in thread_ids
        assert legacy_tid in thread_ids

    async def test_write_without_legacy_works_normally(self, store, fake_redis):
        """Regression: the migration branch must not break the common path
        where no legacy key exists."""
        api_key = "fresh-user"
        tid = uuid4()
        await store.append_turn(tid, api_key, _turn("hi"))

        import hashlib

        tenant = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        raw = await fake_redis.get(f"aim:{tenant}:user_threads")
        assert raw is not None
        index = orjson.loads(raw)
        assert len(index) == 1
        assert index[0]["thread_id"] == str(tid)


class TestDeleteRetiresLegacy:
    async def test_delete_removes_legacy_index(self, store, fake_redis):
        """Even if the only record of a thread is in the legacy index, a
        delete must nuke the legacy key so it can't resurface on list."""
        api_key = "deleting-user"
        tid = uuid4()

        # Seed thread data + legacy index.
        ts = datetime.now(timezone.utc).isoformat()
        await store.append_turn(tid, api_key, _turn("first"))
        # Force a legacy-only state by copying the new index into legacy and
        # wiping new.
        import hashlib

        tenant = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        new_name = f"aim:{tenant}:user_threads"
        legacy_name = f"aim:user_threads:{tenant}"
        raw = await fake_redis.get(new_name)
        await fake_redis.setex(legacy_name, 3600, raw)
        await fake_redis.delete(new_name)

        # Now delete — must clear both.
        ok = await store.delete_thread(tid, api_key)
        assert ok is True
        assert await fake_redis.get(legacy_name) is None

        # Subsequent list must not resurface the thread.
        summaries = await store.list_threads(api_key)
        assert summaries == []


class TestTenantIsolation:
    async def test_two_tenants_do_not_collide_under_tenant_prefix(self, store, fake_redis):
        """Structural isolation: two different api_keys must never touch the
        same Redis key after Phase 6."""
        tid_a = uuid4()
        tid_b = uuid4()
        await store.append_turn(tid_a, "tenant-a", _turn("a"))
        await store.append_turn(tid_b, "tenant-b", _turn("b"))

        sum_a = await store.list_threads("tenant-a")
        sum_b = await store.list_threads("tenant-b")

        assert {str(s.thread_id) for s in sum_a} == {str(tid_a)}
        assert {str(s.thread_id) for s in sum_b} == {str(tid_b)}
