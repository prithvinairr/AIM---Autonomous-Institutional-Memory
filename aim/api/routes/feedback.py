"""Feedback route — thumbs-up / thumbs-down signals on query responses.

POST /query/{query_id}/feedback → submit feedback for a cached response
GET  /query/{query_id}/feedback → retrieve stored feedback (if any)
"""
from __future__ import annotations

import hmac
from uuid import UUID, uuid4
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, HTTPException, status

from aim.api.deps import AuthDep, hash_api_key
from aim.config import get_settings
from aim.schemas.feedback import FeedbackRequest, FeedbackResponse, StoredFeedback
from aim.utils.cache import get_response_cache
from aim.utils.metrics import FEEDBACK_TOTAL
from aim.utils.tenant_keys import tenant_id_for

log = structlog.get_logger(__name__)
router = APIRouter(tags=["feedback"])


@router.post(
    "/query/{query_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback for a query response",
)
async def submit_feedback(
    query_id: UUID,
    body: FeedbackRequest,
    api_key: AuthDep,
) -> FeedbackResponse:
    cache = get_response_cache()
    settings = get_settings()
    tenant_id = tenant_id_for(api_key)

    # Verify the query exists (prevent feedback on phantom IDs).
    # Phase 6: reads from the caller's tenant bucket with a legacy fallback
    # so queries cached before the tenant-key upgrade still validate.
    cached = await cache.get_tenanted(tenant_id, str(query_id))
    if cached is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No cached response found for query_id={query_id}. "
                "Feedback can only be submitted for responses within the cache TTL."
            ),
        )

    feedback_id = uuid4()
    now = datetime.now(timezone.utc)

    stored = StoredFeedback(
        feedback_id=str(feedback_id),
        query_id=str(query_id),
        rating=body.rating,
        comment=body.comment,
        api_key_hash=hash_api_key(api_key),
        created_at=now,
    )

    # Store with the dedicated feedback TTL (default 90 days), independently
    # of the query response TTL (default 1 hour).
    feedback_key = f"feedback:{query_id}"
    # Phase 6: per-tenant feedback bucket so two tenants submitting feedback
    # for colliding query IDs never overwrite each other.
    await cache.set_tenanted_with_ttl(
        tenant_id,
        feedback_key,
        stored.model_dump(mode="json"),   # dict directly — no JSON round-trip
        settings.feedback_ttl_seconds,
    )

    FEEDBACK_TOTAL.labels(rating=body.rating.value).inc()

    log.info(
        "feedback.submitted",
        query_id=str(query_id),
        rating=body.rating.value,
        api_key_hash=hash_api_key(api_key),
        has_comment=body.comment is not None,
    )

    return FeedbackResponse(
        feedback_id=feedback_id,
        query_id=query_id,
        rating=body.rating,
        stored=True,
        created_at=now,
    )


@router.get(
    "/query/{query_id}/feedback",
    response_model=StoredFeedback,
    summary="Retrieve stored feedback for a query",
)
async def get_feedback(query_id: UUID, api_key: AuthDep) -> StoredFeedback:
    cache = get_response_cache()
    # Phase 6: reads from the caller's tenant bucket with a legacy fallback
    # so feedback written before the upgrade stays retrievable.
    raw = await cache.get_tenanted(tenant_id_for(api_key), f"feedback:{query_id}")

    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No feedback found for query_id={query_id}.",
        )

    stored = StoredFeedback.model_validate(raw)

    # Only the submitter can read their own feedback
    if not hmac.compare_digest(stored.api_key_hash, hash_api_key(api_key)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )

    return stored
