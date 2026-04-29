"""Integration tests for /api/v1/conversations/* routes."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from aim.api.deps import hash_api_key
from aim.schemas.conversation import ConversationThread, ConversationTurn, ThreadSummary
from tests.conftest import TEST_API_KEY


# ── Helpers ───────────────────────────────────────────────────────────────────

def _thread(api_key_hash: str | None = None) -> ConversationThread:
    now = datetime.now(timezone.utc)
    turn = ConversationTurn(
        query_id=uuid4(),
        user_message="What is the deploy process?",
        assistant_message="It uses GitHub Actions. [SRC:src-1]",
        reasoning_depth="standard",
        latency_ms=800.0,
        confidence=0.88,
        source_count=2,
        created_at=now,
    )
    return ConversationThread(
        thread_id=uuid4(),
        api_key_hash=api_key_hash or hash_api_key(TEST_API_KEY),
        turns=[turn],
        created_at=now,
        updated_at=now,
    )


def _summary(thread: ConversationThread) -> ThreadSummary:
    return ThreadSummary(
        thread_id=thread.thread_id,
        turn_count=thread.turn_count,
        last_query=thread.last_query,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


# ── GET /api/v1/conversations ─────────────────────────────────────────────────

async def test_list_threads_returns_200_with_empty_list(client):
    with patch("aim.api.routes.conversations.get_conversation_store") as mock_fn:
        mock_store = MagicMock()
        mock_store.list_threads = AsyncMock(return_value=[])
        mock_fn.return_value = mock_store

        response = await client.get("/api/v1/conversations")

    assert response.status_code == 200
    assert response.json() == []


async def test_list_threads_returns_summaries(client):
    thread = _thread()
    summary = _summary(thread)

    with patch("aim.api.routes.conversations.get_conversation_store") as mock_fn:
        mock_store = MagicMock()
        mock_store.list_threads = AsyncMock(return_value=[summary])
        mock_fn.return_value = mock_store

        response = await client.get("/api/v1/conversations")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["thread_id"] == str(thread.thread_id)
    assert data[0]["turn_count"] == 1
    assert data[0]["last_query"] == "What is the deploy process?"


async def test_list_threads_requires_api_key(test_app):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as anon:
        response = await anon.get("/api/v1/conversations")
    assert response.status_code == 401


# ── GET /api/v1/conversations/{thread_id} ────────────────────────────────────

async def test_get_thread_returns_200(client):
    thread = _thread()

    with patch("aim.api.routes.conversations.get_conversation_store") as mock_fn:
        mock_store = MagicMock()
        mock_store.get_thread = AsyncMock(return_value=thread)
        mock_fn.return_value = mock_store

        response = await client.get(f"/api/v1/conversations/{thread.thread_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] == str(thread.thread_id)
    assert len(data["turns"]) == 1
    assert data["turns"][0]["user_message"] == "What is the deploy process?"


async def test_get_thread_404_when_not_found(client):
    with patch("aim.api.routes.conversations.get_conversation_store") as mock_fn:
        mock_store = MagicMock()
        mock_store.get_thread = AsyncMock(return_value=None)
        mock_fn.return_value = mock_store

        response = await client.get(f"/api/v1/conversations/{uuid4()}")

    assert response.status_code == 404


async def test_get_thread_403_for_different_api_key(client):
    """A thread owned by a different API key prefix must return 403."""
    thread = _thread(api_key_hash=hash_api_key("wrong-key-zzzzzzzz"))

    with patch("aim.api.routes.conversations.get_conversation_store") as mock_fn:
        mock_store = MagicMock()
        mock_store.get_thread = AsyncMock(return_value=thread)
        mock_fn.return_value = mock_store

        response = await client.get(f"/api/v1/conversations/{thread.thread_id}")

    assert response.status_code == 403


# ── DELETE /api/v1/conversations/{thread_id} ─────────────────────────────────

async def test_delete_thread_returns_204(client):
    thread = _thread()

    with patch("aim.api.routes.conversations.get_conversation_store") as mock_fn:
        mock_store = MagicMock()
        mock_store.get_thread = AsyncMock(return_value=thread)
        mock_store.delete_thread = AsyncMock(return_value=True)
        mock_fn.return_value = mock_store

        response = await client.delete(f"/api/v1/conversations/{thread.thread_id}")

    assert response.status_code == 204


async def test_delete_thread_403_for_different_api_key(client):
    thread = _thread(api_key_hash=hash_api_key("wrong-key-zzzzzzzz"))

    with patch("aim.api.routes.conversations.get_conversation_store") as mock_fn:
        mock_store = MagicMock()
        mock_store.get_thread = AsyncMock(return_value=thread)
        mock_fn.return_value = mock_store

        response = await client.delete(f"/api/v1/conversations/{thread.thread_id}")

    assert response.status_code == 403


async def test_delete_nonexistent_thread_returns_204(client):
    """Deleting a thread that doesn't exist is idempotent (not an error)."""
    with patch("aim.api.routes.conversations.get_conversation_store") as mock_fn:
        mock_store = MagicMock()
        mock_store.get_thread = AsyncMock(return_value=None)
        mock_store.delete_thread = AsyncMock(return_value=False)
        mock_fn.return_value = mock_store

        response = await client.delete(f"/api/v1/conversations/{uuid4()}")

    # Thread not found → ownership check skipped → 204 (idempotent delete)
    assert response.status_code == 204
