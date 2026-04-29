"""Unit tests for ConversationStore.

All tests use fakeredis so no real Redis is required.
The store is instantiated directly — no FastAPI app needed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4, UUID

import fakeredis.aioredis
import pytest

from aim.schemas.conversation import ConversationTurn, ThreadSummary
from aim.utils.conversation_store import ConversationStore


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(fake_redis) -> ConversationStore:
    s = ConversationStore(redis_url="redis://localhost:6379", ttl_seconds=3600, max_turns=5)
    s._redis = fake_redis
    s._ok = True
    return s


def _turn(query: str = "What is AIM?", answer: str = "AIM is a RAG system.") -> ConversationTurn:
    return ConversationTurn(
        query_id=uuid4(),
        user_message=query,
        assistant_message=answer,
        reasoning_depth="standard",
        latency_ms=500.0,
        confidence=0.9,
        source_count=3,
    )


# ── get_history ───────────────────────────────────────────────────────────────

async def test_get_history_returns_empty_for_nonexistent_thread(store):
    history = await store.get_history(uuid4())
    assert history == []


async def test_get_history_returns_alternating_role_content_pairs(store):
    tid = uuid4()
    api_key = "test-key-abc"
    turn = _turn("What is AIM?", "AIM is great.")
    await store.append_turn(tid, api_key, turn)

    history = await store.get_history(tid)
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "What is AIM?"}
    assert history[1] == {"role": "assistant", "content": "AIM is great."}


async def test_get_history_caps_at_max_turns(store):
    """max_turns=5 means only the 5 most recent turns are returned."""
    tid = uuid4()
    api_key = "test-key-abc"
    for i in range(8):
        await store.append_turn(tid, api_key, _turn(f"q{i}", f"a{i}"))

    history = await store.get_history(tid)
    # 5 turns × 2 messages each = 10 items
    assert len(history) == 10
    # The oldest turns (q0–q2) should be dropped
    user_messages = [m["content"] for m in history if m["role"] == "user"]
    assert "q0" not in user_messages
    assert "q7" in user_messages


async def test_get_history_returns_empty_when_redis_unavailable():
    store = ConversationStore(redis_url="redis://invalid:6379", ttl_seconds=3600, max_turns=5)
    # _ok stays False — no connect() called
    history = await store.get_history(uuid4())
    assert history == []


# ── get_history_for_key ───────────────────────────────────────────────────────

async def test_get_history_for_key_returns_history_for_matching_key(store):
    tid = uuid4()
    api_key = "correct-key-xyz"
    await store.append_turn(tid, api_key, _turn())

    history = await store.get_history_for_key(tid, api_key)
    assert len(history) == 2


async def test_get_history_for_key_returns_empty_for_nonexistent_thread(store):
    history = await store.get_history_for_key(uuid4(), "any-key-xxx")
    assert history == []


async def test_get_history_for_key_raises_on_wrong_api_key(store):
    tid = uuid4()
    await store.append_turn(tid, "owner-key-abc", _turn())

    with pytest.raises(PermissionError, match=str(tid)):
        await store.get_history_for_key(tid, "other-key-xyz")


async def test_get_history_for_key_rejects_different_key_even_same_prefix(store):
    """Ownership uses SHA-256 hash — different keys with same prefix are rejected."""
    tid = uuid4()
    owner_key = "abcdefgh-longersuffix"
    await store.append_turn(tid, owner_key, _turn())

    # Same first-8 chars but different full key → different hash → rejected
    different_key = "abcdefgh-differentsuffix"
    with pytest.raises(PermissionError):
        await store.get_history_for_key(tid, different_key)

    # Same exact key → accepted
    history = await store.get_history_for_key(tid, owner_key)
    assert len(history) == 2


# ── append_turn ───────────────────────────────────────────────────────────────

async def test_append_turn_creates_new_thread(store):
    tid = uuid4()
    await store.append_turn(tid, "key-abc123", _turn())
    thread = await store.get_thread(tid)
    assert thread is not None
    assert len(thread.turns) == 1


async def test_append_turn_appends_to_existing_thread(store):
    tid = uuid4()
    api_key = "key-abc123"
    await store.append_turn(tid, api_key, _turn("q1", "a1"))
    await store.append_turn(tid, api_key, _turn("q2", "a2"))
    thread = await store.get_thread(tid)
    assert thread is not None
    assert len(thread.turns) == 2
    assert thread.turns[0].user_message == "q1"
    assert thread.turns[1].user_message == "q2"


async def test_append_turn_preserves_original_created_at(store):
    tid = uuid4()
    api_key = "key-abc123"
    await store.append_turn(tid, api_key, _turn("first"))
    thread_after_first = await store.get_thread(tid)
    assert thread_after_first is not None
    original_created_at = thread_after_first.created_at

    await store.append_turn(tid, api_key, _turn("second"))
    thread_after_second = await store.get_thread(tid)
    assert thread_after_second is not None
    assert thread_after_second.created_at == original_created_at


# ── list_threads ──────────────────────────────────────────────────────────────

async def test_list_threads_returns_empty_for_new_key(store):
    summaries = await store.list_threads("brand-new-key-abc")
    assert summaries == []


async def test_list_threads_returns_summary_after_append(store):
    tid = uuid4()
    api_key = "list-test-key1"
    await store.append_turn(tid, api_key, _turn("hello", "world"))

    summaries = await store.list_threads(api_key)
    assert len(summaries) == 1
    s = summaries[0]
    assert s.thread_id == tid
    assert s.turn_count == 1
    assert s.last_query == "hello"


async def test_list_threads_is_single_redis_read(store, fake_redis, monkeypatch):
    """list_threads must not call _load_thread — it reads from the index only."""
    tid = uuid4()
    api_key = "efficiency-key-x"
    await store.append_turn(tid, api_key, _turn())

    load_calls: list = []
    original = store._load_thread

    async def _spy(thread_id):
        load_calls.append(thread_id)
        return await original(thread_id)

    monkeypatch.setattr(store, "_load_thread", _spy)

    await store.list_threads(api_key)
    assert load_calls == [], "list_threads must not call _load_thread"


async def test_list_threads_newest_first(store):
    api_key = "order-test-key1"
    tid1, tid2 = uuid4(), uuid4()
    await store.append_turn(tid1, api_key, _turn("older query"))
    await store.append_turn(tid2, api_key, _turn("newer query"))

    summaries = await store.list_threads(api_key)
    assert summaries[0].thread_id == tid2
    assert summaries[1].thread_id == tid1


# ── delete_thread ─────────────────────────────────────────────────────────────

async def test_delete_thread_removes_from_storage(store):
    tid = uuid4()
    api_key = "del-key-abc1"
    await store.append_turn(tid, api_key, _turn())
    await store.delete_thread(tid, api_key)
    assert await store.get_thread(tid) is None


async def test_delete_thread_removes_from_index(store):
    tid = uuid4()
    api_key = "del-index-key1"
    await store.append_turn(tid, api_key, _turn())
    await store.delete_thread(tid, api_key)
    summaries = await store.list_threads(api_key)
    assert all(s.thread_id != tid for s in summaries)


async def test_delete_nonexistent_thread_returns_false(store):
    result = await store.delete_thread(uuid4(), "any-key-abc1")
    assert result is False


# ── connect / close lifecycle ────────────────────────────────────────────────

async def test_connect_success_marks_ok():
    """connect() sets _ok=True when Redis is reachable (fakeredis)."""
    store = ConversationStore(redis_url="redis://localhost:6379", ttl_seconds=3600, max_turns=5)

    # Inject a fakeredis client directly, then verify ping succeeds
    fake = fakeredis.aioredis.FakeRedis()
    from unittest.mock import AsyncMock, patch
    with patch("redis.asyncio.from_url", AsyncMock(return_value=fake)):
        await store.connect()

    assert store._ok is True
    assert store._redis is fake


async def test_connect_failure_sets_ok_false():
    """connect() gracefully handles connection failure."""
    store = ConversationStore(redis_url="redis://bad:6379", ttl_seconds=3600, max_turns=5)

    from unittest.mock import AsyncMock, patch
    with patch("redis.asyncio.from_url", AsyncMock(side_effect=ConnectionError("refused"))):
        await store.connect()

    assert store._ok is False


async def test_close_calls_aclose():
    """close() calls aclose() on the Redis client."""
    from unittest.mock import AsyncMock

    store = ConversationStore(redis_url="redis://localhost:6379", ttl_seconds=3600, max_turns=5)
    mock_redis = AsyncMock()
    store._redis = mock_redis

    await store.close()
    mock_redis.aclose.assert_called_once()


async def test_close_noop_without_redis():
    """close() is a no-op when no Redis client exists."""
    store = ConversationStore(redis_url="redis://localhost:6379", ttl_seconds=3600, max_turns=5)
    store._redis = None
    await store.close()  # should not raise


# ── Error resilience ─────────────────────────────────────────────────────────

async def test_load_thread_returns_none_on_redis_error():
    """_load_thread returns None when Redis raises."""
    from unittest.mock import AsyncMock

    store = ConversationStore(redis_url="redis://localhost:6379", ttl_seconds=3600, max_turns=5)
    store._ok = True
    store._redis = AsyncMock()
    store._redis.get = AsyncMock(side_effect=ConnectionError("lost connection"))

    result = await store._load_thread(uuid4())
    assert result is None


async def test_save_thread_handles_redis_error():
    """_save_thread logs a warning but does not raise on Redis error."""
    from unittest.mock import AsyncMock
    from aim.schemas.conversation import ConversationThread

    store = ConversationStore(redis_url="redis://localhost:6379", ttl_seconds=3600, max_turns=5)
    store._ok = True
    store._redis = AsyncMock()
    store._redis.setex = AsyncMock(side_effect=ConnectionError("redis down"))

    thread = ConversationThread(
        thread_id=uuid4(),
        api_key_hash="abc",
        turns=[_turn()],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await store._save_thread(thread)  # should not raise


async def test_save_thread_noop_when_not_ok():
    """_save_thread is a no-op when Redis is unavailable."""
    from unittest.mock import AsyncMock
    from aim.schemas.conversation import ConversationThread

    store = ConversationStore(redis_url="redis://localhost:6379", ttl_seconds=3600, max_turns=5)
    store._ok = False
    store._redis = AsyncMock()

    thread = ConversationThread(
        thread_id=uuid4(),
        api_key_hash="abc",
        turns=[_turn()],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await store._save_thread(thread)
    store._redis.setex.assert_not_called()


async def test_append_turn_noop_when_not_ok():
    """append_turn is a no-op when Redis is unavailable."""
    store = ConversationStore(redis_url="redis://localhost:6379", ttl_seconds=3600, max_turns=5)
    store._ok = False
    await store.append_turn(uuid4(), "key", _turn())  # should not raise


async def test_update_index_noop_when_not_ok():
    """_update_index is a no-op when Redis is unavailable."""
    from aim.schemas.conversation import ConversationThread

    store = ConversationStore(redis_url="redis://localhost:6379", ttl_seconds=3600, max_turns=5)
    store._ok = False

    thread = ConversationThread(
        thread_id=uuid4(),
        api_key_hash="abc",
        turns=[_turn()],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await store._update_index("key", thread)  # should not raise


async def test_list_threads_handles_redis_error():
    """list_threads returns [] on Redis error."""
    from unittest.mock import AsyncMock

    store = ConversationStore(redis_url="redis://localhost:6379", ttl_seconds=3600, max_turns=5)
    store._ok = True
    store._redis = AsyncMock()
    store._redis.get = AsyncMock(side_effect=ConnectionError("redis down"))

    result = await store.list_threads("some-key")
    assert result == []


async def test_delete_thread_returns_false_when_not_ok_direct():
    """delete_thread returns False when Redis is unavailable."""
    store = ConversationStore(redis_url="redis://localhost:6379", ttl_seconds=3600, max_turns=5)
    store._ok = False

    result = await store.delete_thread(uuid4(), "key")
    assert result is False


async def test_list_threads_pagination(store):
    """list_threads respects limit and offset parameters."""
    api_key = "paginate-key-1"
    tids = []
    for i in range(8):
        tid = uuid4()
        tids.append(tid)
        await store.append_turn(tid, api_key, _turn(f"q{i}", f"a{i}"))

    # Page 2: offset=3, limit=3
    result = await store.list_threads(api_key, limit=3, offset=3)
    assert len(result) == 3


# ── WATCH conflict retry in _update_index (lines 139-143) ───────────────────

async def test_update_index_retries_on_watch_conflict(store, fake_redis, monkeypatch):
    """_update_index retries when a WatchError is raised, then succeeds."""
    from aim.schemas.conversation import ConversationThread

    tid = uuid4()
    thread = ConversationThread(
        thread_id=tid,
        api_key_hash="abc123",
        turns=[_turn()],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    call_count = 0
    original_pipeline = fake_redis.pipeline

    def patched_pipeline(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First attempt: raise a WatchError to trigger retry
            raise Exception("WATCH variable modified")
        return original_pipeline(**kwargs)

    monkeypatch.setattr(fake_redis, "pipeline", patched_pipeline)
    await store._update_index("test-key-watch", thread)

    # Should have retried (call_count >= 2) and ultimately succeeded
    assert call_count >= 2
    summaries = await store.list_threads("test-key-watch")
    assert len(summaries) == 1
    assert summaries[0].thread_id == tid


# ── Turns truncation warning at 500+ turns (line 230) ───────────────────────

async def test_append_turn_truncates_at_500_turns(store):
    """When a thread exceeds 500 turns, it is truncated to 500."""
    tid = uuid4()
    api_key = "truncation-key-1"

    # Build a thread with 500 turns by directly saving it
    from aim.schemas.conversation import ConversationThread
    import orjson

    turns_list = [_turn(f"q{i}", f"a{i}") for i in range(500)]
    thread = ConversationThread(
        thread_id=tid,
        api_key_hash="abc",
        turns=turns_list,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    # Save directly to Redis to set up 500 turns
    await store._redis.setex(
        f"aim:conv:{tid}",
        store._ttl,
        orjson.dumps(thread.model_dump(mode="json")),
    )

    # Now append a 501st turn — should trigger truncation
    await store.append_turn(tid, api_key, _turn("q500", "a500"))
    result = await store.get_thread(tid)
    assert result is not None
    assert len(result.turns) == 500  # capped at 500
    # The oldest turn (q0) should have been dropped
    assert result.turns[0].user_message == "q1"
    assert result.turns[-1].user_message == "q500"


# ── WATCH conflict retry in append_turn (lines 254-262) ─────────────────────

async def test_append_turn_retries_on_watch_conflict(store, fake_redis, monkeypatch):
    """append_turn retries when a WatchError is raised during the transaction."""
    tid = uuid4()
    api_key = "watch-append-key"

    call_count = 0
    original_pipeline = fake_redis.pipeline

    def patched_pipeline(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("WATCH variable modified")
        return original_pipeline(**kwargs)

    monkeypatch.setattr(fake_redis, "pipeline", patched_pipeline)
    await store.append_turn(tid, api_key, _turn("watchq", "watcha"))

    # Should have retried
    assert call_count >= 2
    thread = await store.get_thread(tid)
    assert thread is not None
    assert len(thread.turns) == 1
    assert thread.turns[0].user_message == "watchq"


# ── list_threads when _ok is False (line 292) ───────────────────────────────

async def test_list_threads_returns_empty_when_not_ok():
    """list_threads returns [] immediately when Redis is unavailable."""
    store = ConversationStore(redis_url="redis://invalid:6379", ttl_seconds=3600, max_turns=5)
    store._ok = False
    result = await store.list_threads("any-key-abc")
    assert result == []


# ── Exception in list_threads JSON parsing (lines 321-322) ──────────────────

async def test_list_threads_skips_malformed_index_entries(store, fake_redis):
    """list_threads silently skips index entries that fail to parse into ThreadSummary."""
    import orjson

    api_key = "malformed-key-1"
    index_key = store._index_key(api_key)
    good_tid = uuid4()
    now = datetime.now(timezone.utc)

    index = [
        # Valid entry
        {
            "thread_id": str(good_tid),
            "updated_at": now.isoformat(),
            "created_at": now.isoformat(),
            "last_query": "hello",
            "turn_count": 1,
        },
        # Malformed entry — missing thread_id (will fail UUID parsing)
        {
            "updated_at": "not-a-date",
        },
    ]
    await fake_redis.setex(index_key, 3600, orjson.dumps(index))

    summaries = await store.list_threads(api_key)
    # Only the valid entry should be returned
    assert len(summaries) == 1
    assert summaries[0].thread_id == good_tid


# ── WATCH conflict retry in delete_thread (lines 356-362) ───────────────────

async def test_delete_thread_retries_on_watch_conflict(store, fake_redis, monkeypatch):
    """delete_thread retries when a WatchError is raised, then succeeds."""
    tid = uuid4()
    api_key = "watch-delete-key"
    await store.append_turn(tid, api_key, _turn("dq", "da"))

    call_count = 0
    original_pipeline = fake_redis.pipeline

    def patched_pipeline(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("WATCH variable modified")
        return original_pipeline(**kwargs)

    monkeypatch.setattr(fake_redis, "pipeline", patched_pipeline)
    result = await store.delete_thread(tid, api_key)

    # Should have retried and succeeded on second attempt
    assert call_count >= 2
    assert result is True
    assert await store.get_thread(tid) is None
