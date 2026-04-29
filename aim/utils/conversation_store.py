"""Redis-backed conversation thread store.

Key schema
──────────
``aim:conv:{thread_id}``        JSON-serialised ConversationThread (full turns list)
``aim:user_threads:{key_hash}`` JSON list of {thread_id, updated_at} — index per API key

Thread TTL is controlled by ``settings.conversation_ttl_seconds`` (default 7 days).
The index entry is refreshed on every write so it matches the thread TTL.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import orjson
import structlog

from aim.api.deps import hash_api_key
from aim.schemas.conversation import ConversationThread, ConversationTurn, ThreadSummary
from aim.utils.tenant_keys import legacy_key, tenant_id_for, tenant_key

log = structlog.get_logger(__name__)

_MAX_INDEX_THREADS = 200  # max threads stored per API key in the index


class ConversationStore:
    """Manages multi-turn conversation history in Redis.

    Falls back gracefully to no-ops when Redis is unavailable so the query
    pipeline always succeeds even without conversation persistence.
    """

    def __init__(self, redis_url: str, ttl_seconds: int, max_turns: int) -> None:
        self._redis_url = redis_url
        self._ttl = ttl_seconds
        self._max_turns = max_turns
        self._redis: Any = None
        self._ok = False

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
            self._ok = True
            log.info("conversation_store.connected")
        except Exception as exc:
            log.warning("conversation_store.unavailable", error=str(exc))
            self._ok = False

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _thread_key(self, thread_id: UUID) -> str:
        return f"aim:conv:{thread_id}"

    def _index_key(self, api_key: str) -> str:
        """Canonical post-Phase-6 key: ``aim:{tenant_id}:user_threads``.

        ``tenant_id`` is the 16-char SHA truncation of the api_key — same
        width as the pre-Phase-6 suffix, so migrated and legacy keys carry
        the same identifying fingerprint for the same caller.
        """
        return tenant_key("user_threads", tenant_id=tenant_id_for(api_key))

    def _legacy_index_key(self, api_key: str) -> str:
        """Pre-Phase-6 key shape: ``aim:user_threads:{key_hash}``.

        Used only as a read-fallback during migration. ``_update_index`` and
        ``delete_thread`` proactively delete this key so zombie data doesn't
        resurface via fallback after the caller's state was rewritten.
        """
        h = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        return legacy_key("user_threads", h)

    async def _load_thread(self, thread_id: UUID) -> ConversationThread | None:
        if not self._ok:
            return None
        try:
            raw = await self._redis.get(self._thread_key(thread_id))
            if raw is None:
                return None
            return ConversationThread.model_validate(orjson.loads(raw))
        except Exception as exc:
            log.warning("conversation_store.load_failed", thread_id=str(thread_id), error=str(exc))
            return None

    async def _save_thread(self, thread: ConversationThread) -> None:
        if not self._ok:
            return
        try:
            await self._redis.setex(
                self._thread_key(thread.thread_id),
                self._ttl,
                orjson.dumps(thread.model_dump(mode="json")),
            )
        except Exception as exc:
            log.warning("conversation_store.save_failed", thread_id=str(thread.thread_id), error=str(exc))

    async def _update_index(self, api_key: str, thread: ConversationThread) -> None:
        """Persist a lightweight summary for this thread into the per-key index.

        Uses optimistic locking (WATCH/MULTI/EXEC) to make the read-filter-
        insert-trim-write atomic, preventing lost updates under concurrent
        requests for the same API key.  Falls back to a simple overwrite if
        the WATCH detects a conflict (the next write will reconcile).

        The index entry carries all fields needed to build a ``ThreadSummary``
        without loading the full thread object — so ``list_threads`` is a
        single Redis read instead of N+1.
        """
        if not self._ok:
            return
        key = self._index_key(api_key)
        legacy = self._legacy_index_key(api_key)
        tid_str = str(thread.thread_id)
        entry: dict[str, Any] = {
            "thread_id": tid_str,
            "updated_at": thread.updated_at.isoformat(),
            "created_at": thread.created_at.isoformat(),
            "last_query": thread.last_query,
            "turn_count": thread.turn_count,
        }
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with self._redis.pipeline(transaction=True) as pipe:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    index: list[dict[str, Any]] = orjson.loads(raw) if raw else []

                    # Phase 6 migration: first write after upgrade sees an
                    # empty NEW key while legacy may still hold this caller's
                    # threads. Fold those in once so nothing is lost, then
                    # let the subsequent ``pipe.delete(legacy)`` retire it.
                    if not index:
                        try:
                            legacy_raw = await self._redis.get(legacy)
                            if legacy_raw:
                                index = orjson.loads(legacy_raw)
                        except Exception:
                            # Legacy miss is non-fatal — proceed with empty.
                            index = []

                    # Remove stale entry for this thread, then prepend the fresh one
                    index = [e for e in index if e.get("thread_id") != tid_str]
                    index.insert(0, entry)
                    index = index[:_MAX_INDEX_THREADS]

                    pipe.multi()
                    pipe.setex(key, self._ttl, orjson.dumps(index))
                    # Legacy retirement: idempotent — no-op if already gone.
                    pipe.delete(legacy)
                    await pipe.execute()
                    return  # success
            except Exception as exc:
                if "WATCH" in str(exc).upper() and attempt < max_retries - 1:
                    continue  # retry on conflict
                log.warning("conversation_store.index_failed", error=str(exc))
                return

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_history(self, thread_id: UUID) -> list[dict[str, str]]:
        """Return the last ``max_turns`` exchanges as role/content dicts.

        Only returns the most recent turns so the context window stays bounded.
        Format: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
        """
        thread = await self._load_thread(thread_id)
        if not thread:
            return []

        recent = thread.turns[-self._max_turns:]
        history: list[dict[str, str]] = []
        for turn in recent:
            history.append({"role": "user", "content": turn.user_message})
            history.append({"role": "assistant", "content": turn.assistant_message})
        return history

    async def get_history_for_key(
        self, thread_id: UUID, api_key: str
    ) -> list[dict[str, str]]:
        """Return history only if the thread belongs to ``api_key``.

        Returns an empty list (rather than raising) when the thread doesn't
        exist — callers treat a missing thread as a new conversation.
        Raises ``PermissionError`` when the thread exists but the key doesn't
        match, so the route can return HTTP 403.
        """
        thread = await self._load_thread(thread_id)
        if thread is None:
            return []

        caller_hash = hash_api_key(api_key)
        if thread.api_key_hash and not hmac.compare_digest(thread.api_key_hash, caller_hash):
            raise PermissionError(
                f"Thread {thread_id} belongs to a different API key."
            )

        recent = thread.turns[-self._max_turns:]
        history: list[dict[str, str]] = []
        for turn in recent:
            history.append({"role": "user", "content": turn.user_message})
            history.append({"role": "assistant", "content": turn.assistant_message})
        return history

    async def append_turn(
        self,
        thread_id: UUID,
        api_key: str,
        turn: ConversationTurn,
    ) -> None:
        """Append a completed turn to the thread, creating it if necessary.

        Uses optimistic locking (WATCH/MULTI/EXEC) on the thread key so that
        concurrent appends on the same thread don't lose turns.  Falls back to
        a simple overwrite after ``max_retries`` conflicts.
        """
        if not self._ok:
            return

        now = datetime.now(timezone.utc)
        key_hash = hash_api_key(api_key)
        thread_key = self._thread_key(thread_id)
        max_retries = 3

        for attempt in range(max_retries):
            try:
                async with self._redis.pipeline(transaction=True) as pipe:
                    await pipe.watch(thread_key)

                    # Atomic read inside the WATCH window
                    raw = await pipe.get(thread_key)
                    if raw is None:
                        thread = ConversationThread(
                            thread_id=thread_id,
                            api_key_hash=key_hash,
                            turns=[turn],
                            created_at=now,
                            updated_at=now,
                        )
                    else:
                        existing = ConversationThread.model_validate(orjson.loads(raw))
                        all_turns = [*existing.turns, turn]
                        if len(all_turns) > 500:
                            log.warning(
                                "conversation_store.turns_truncated",
                                thread_id=str(thread_id),
                                total=len(all_turns),
                                kept=500,
                                dropped=len(all_turns) - 500,
                            )
                        turns = all_turns[-500:]
                        thread = ConversationThread(
                            thread_id=thread_id,
                            api_key_hash=existing.api_key_hash,
                            turns=turns,
                            created_at=existing.created_at,
                            updated_at=now,
                        )

                    pipe.multi()
                    pipe.setex(
                        thread_key,
                        self._ttl,
                        orjson.dumps(thread.model_dump(mode="json")),
                    )
                    await pipe.execute()
                    break  # success
            except Exception as exc:
                if "WATCH" in str(exc).upper() and attempt < max_retries - 1:
                    continue  # retry on conflict
                log.warning(
                    "conversation_store.append_failed",
                    thread_id=str(thread_id),
                    error=str(exc),
                )
                return

        await self._update_index(api_key, thread)

        log.debug(
            "conversation_store.turn_saved",
            thread_id=str(thread_id),
            turns=len(thread.turns),
        )

    async def get_thread(self, thread_id: UUID) -> ConversationThread | None:
        """Return the full thread object."""
        return await self._load_thread(thread_id)

    async def list_threads(
        self,
        api_key: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ThreadSummary]:
        """Return thread summaries for an API key, newest first.

        This is a single Redis read — the index carries all summary fields
        so we never need to load the full thread objects.

        Args:
            limit:  Maximum number of summaries to return (1–100).
            offset: Number of summaries to skip (for pagination).
        """
        if not self._ok:
            return []
        key = self._index_key(api_key)
        try:
            raw = await self._redis.get(key)
            if not raw:
                # Phase 6 fallback: caller hasn't triggered a write since the
                # upgrade, so their index still lives under the legacy key.
                # Read it verbatim; the next ``_update_index`` will migrate.
                raw = await self._redis.get(self._legacy_index_key(api_key))
                if not raw:
                    return []
            index: list[dict[str, Any]] = orjson.loads(raw)
        except Exception as exc:
            log.warning("conversation_store.list_failed", error=str(exc))
            return []

        # Apply pagination slice before building ThreadSummary objects
        index = index[offset: offset + max(1, min(limit, 100))]

        summaries: list[ThreadSummary] = []
        for entry in index:
            try:
                updated_at_str = entry["updated_at"]
                # created_at may be absent in index entries written by older versions
                created_at_str = entry.get("created_at", updated_at_str)
                summaries.append(
                    ThreadSummary(
                        thread_id=UUID(entry["thread_id"]),
                        turn_count=entry.get("turn_count", 0),
                        last_query=entry.get("last_query", ""),
                        created_at=datetime.fromisoformat(created_at_str),
                        updated_at=datetime.fromisoformat(updated_at_str),
                    )
                )
            except Exception:
                continue

        return summaries

    async def delete_thread(self, thread_id: UUID, api_key: str) -> bool:
        """Atomically delete a thread and remove it from the user index.

        Uses a Redis pipeline so the thread key deletion and the index
        update are sent in a single round-trip. The WATCH on the index key
        ensures the read-filter-write is conflict-free.
        """
        if not self._ok:
            return False

        thread_key = self._thread_key(thread_id)
        index_key = self._index_key(api_key)
        legacy_index = self._legacy_index_key(api_key)
        tid_str = str(thread_id)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with self._redis.pipeline(transaction=True) as pipe:
                    await pipe.watch(index_key)
                    # Read current index while watched; seed from legacy on
                    # cold NEW so a delete-before-first-write can't leave the
                    # thread stuck in the legacy index.
                    raw = await pipe.get(index_key)
                    index: list[dict[str, Any]] = orjson.loads(raw) if raw else []
                    if not index:
                        try:
                            legacy_raw = await self._redis.get(legacy_index)
                            if legacy_raw:
                                index = orjson.loads(legacy_raw)
                        except Exception:
                            index = []
                    index = [e for e in index if e.get("thread_id") != tid_str]

                    pipe.multi()
                    pipe.delete(thread_key)
                    pipe.setex(index_key, self._ttl, orjson.dumps(index))
                    # Retire the legacy index — idempotent.
                    pipe.delete(legacy_index)
                    results = await pipe.execute()
                    # results[0] = number of keys deleted (0 or 1)
                    return int(results[0]) > 0
            except Exception as exc:
                if "WATCH" in str(exc).upper() and attempt < max_retries - 1:
                    continue
                log.warning("conversation_store.delete_failed", thread_id=tid_str, error=str(exc))
                return False

        return False


# ── Singleton ─────────────────────────────────────────────────────────────────

_store_instance: ConversationStore | None = None


def get_conversation_store() -> ConversationStore:
    global _store_instance
    if _store_instance is None:
        from aim.config import get_settings

        s = get_settings()
        _store_instance = ConversationStore(
            redis_url=s.redis_url,
            ttl_seconds=s.conversation_ttl_seconds,
            max_turns=s.conversation_max_turns,
        )
    return _store_instance
