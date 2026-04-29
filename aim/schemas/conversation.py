"""Conversation thread schemas for multi-turn query sessions."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ConversationTurn(BaseModel):
    """A single user ↔ assistant exchange within a thread."""

    model_config = ConfigDict(frozen=True)

    turn_id: str = Field(default_factory=lambda: str(uuid4()))
    query_id: UUID
    user_message: str
    assistant_message: str
    reasoning_depth: str = "standard"
    latency_ms: float = 0.0
    confidence: float = 0.0
    source_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationThread(BaseModel):
    """Full thread — stored in Redis, returned by the conversations API."""

    thread_id: UUID
    api_key_hash: str  # SHA-256 hash of the full API key for ownership verification
    turns: list[ConversationTurn] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def last_query(self) -> str:
        if self.turns:
            return self.turns[-1].user_message[:200]
        return ""

    @property
    def turn_count(self) -> int:
        return len(self.turns)


class ThreadSummary(BaseModel):
    """Lightweight thread metadata for list endpoints."""

    model_config = ConfigDict(frozen=True)

    thread_id: UUID
    turn_count: int
    last_query: str
    created_at: datetime
    updated_at: datetime
