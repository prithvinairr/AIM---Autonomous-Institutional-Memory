"""Feedback schemas for per-query thumbs-up / thumbs-down signals."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class FeedbackRating(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class FeedbackRequest(BaseModel):
    rating: FeedbackRating
    comment: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional free-text comment explaining the rating.",
    )


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    feedback_id: UUID = Field(default_factory=uuid4)
    query_id: UUID
    rating: FeedbackRating
    stored: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StoredFeedback(BaseModel):
    """Full feedback record persisted in Redis."""

    model_config = ConfigDict(frozen=True)

    feedback_id: str
    query_id: str
    rating: FeedbackRating
    comment: str | None = None
    api_key_hash: str  # SHA-256 hash for ownership verification
    created_at: datetime
