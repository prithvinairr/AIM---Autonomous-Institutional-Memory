"""Conversation thread management routes.

GET  /conversations                    → list threads for the authenticated API key
GET  /conversations/{thread_id}        → full thread with all turns
DELETE /conversations/{thread_id}      → delete thread and remove from index
"""
from __future__ import annotations

import hmac
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Query, Response, status

from aim.api.deps import AuthDep, hash_api_key
from aim.schemas.conversation import ConversationThread, ThreadSummary
from aim.utils.conversation_store import get_conversation_store

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get(
    "",
    response_model=list[ThreadSummary],
    summary="List conversation threads for the authenticated key",
)
async def list_threads(
    api_key: AuthDep,
    limit: int = Query(default=20, ge=1, le=100, description="Max threads to return"),
    offset: int = Query(default=0, ge=0, description="Number of threads to skip"),
) -> list[ThreadSummary]:
    store = get_conversation_store()
    summaries = await store.list_threads(api_key, limit=limit, offset=offset)
    log.debug("conversations.list", api_key_hash=hash_api_key(api_key)[:12], count=len(summaries))
    return summaries


@router.get(
    "/{thread_id}",
    response_model=ConversationThread,
    summary="Retrieve a full conversation thread",
)
async def get_thread(thread_id: UUID, api_key: AuthDep) -> ConversationThread:
    store = get_conversation_store()
    thread = await store.get_thread(thread_id)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread {thread_id} not found or expired.",
        )
    # Verify ownership — thread key hash must match caller's key hash
    caller_hash = hash_api_key(api_key)
    if thread.api_key_hash and not hmac.compare_digest(thread.api_key_hash, caller_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: thread belongs to a different API key.",
        )
    return thread


@router.delete(
    "/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a conversation thread",
)
async def delete_thread(thread_id: UUID, api_key: AuthDep) -> Response:
    store = get_conversation_store()

    # Check ownership before deleting
    thread = await store.get_thread(thread_id)
    caller_hash = hash_api_key(api_key)
    if thread is not None and thread.api_key_hash and not hmac.compare_digest(thread.api_key_hash, caller_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: thread belongs to a different API key.",
        )

    deleted = await store.delete_thread(thread_id, api_key)
    if not deleted and thread is not None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete thread.",
        )
    log.info("conversations.deleted", thread_id=str(thread_id), api_key_hash=hash_api_key(api_key)[:12])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
