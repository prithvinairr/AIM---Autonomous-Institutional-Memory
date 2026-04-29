"""Schemas for LLM-based entity and relationship extraction.

These models represent the *extracted* knowledge before it is mapped to
the canonical ``GraphEntity`` / ``GraphRelationship`` schemas and fed
into the ingest worker.
"""
from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field


# ── Entity types the extraction prompt knows about ───────────────────────────

ENTITY_TYPES = frozenset({
    "Person",
    "Team",
    "Service",
    "Incident",
    "Decision",
    "Document",
    "Project",
    "Component",
})

RELATIONSHIP_TYPES = frozenset({
    "AFFECTS",
    "APPROVED_BY",
    "AUTHORED",
    "BLOCKED_BY",
    "CAUSED_BY",
    "CAUSED",
    "DECIDED",
    "DEPENDS_ON",
    "DEPLOYED_TO",
    "IMPACTED",
    "LED_TO",
    "LEADS",
    "LEADS_PROJECT",
    "MANAGES",
    "MEMBER_OF",
    "MENTIONS",
    "OWNS",
    "MAINTAINS",
    "PART_OF",
    "PROPOSED_BY",
    "REPORTED_BY",
    "REFERENCES",
    "RELATES_TO",
    "RESOLVED_BY",
    "RESPONDED_TO",
    "SUPERSEDES",
    "USED_IN",
})


class ExtractedEntity(BaseModel):
    """A single entity extracted from raw text by the LLM."""

    entity_type: str = Field(
        description="One of the known entity types (Person, Service, …)"
    )
    name: str = Field(description="Canonical name of the entity")
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key–value properties extracted from context",
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="LLM self-assessed confidence in this extraction",
    )

    @property
    def normalized_name(self) -> str:
        """Lowercase, stripped, dedented name for fuzzy matching."""
        return self.name.lower().strip()

    @property
    def fingerprint(self) -> str:
        """Stable hash for deduplication: type + normalized name."""
        raw = f"{self.entity_type}::{self.normalized_name}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class ExtractedRelationship(BaseModel):
    """A relationship between two extracted entities."""

    source_name: str = Field(description="Name of the source entity")
    target_name: str = Field(description="Name of the target entity")
    rel_type: str = Field(description="Relationship type (OWNS, DEPENDS_ON, …)")
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    """Complete extraction output from a single text chunk."""

    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)
    source_text_hash: str = Field(
        default="",
        description="SHA-256 of the source text for idempotency checks",
    )
    source_uri: str = Field(
        default="",
        description="Origin URI (slack://channel/..., jira://..., etc.)",
    )

    @property
    def is_empty(self) -> bool:
        return not self.entities and not self.relationships


class ExtractionBatch(BaseModel):
    """Multiple extraction results batched for ingest."""

    results: list[ExtractionResult] = Field(default_factory=list)

    @property
    def total_entities(self) -> int:
        return sum(len(r.entities) for r in self.results)

    @property
    def total_relationships(self) -> int:
        return sum(len(r.relationships) for r in self.results)
