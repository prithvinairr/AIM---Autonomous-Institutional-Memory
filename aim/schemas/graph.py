"""Schemas for Neo4j graph entities and search results."""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class GraphEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_id: str = Field(default_factory=lambda: str(uuid4()))
    labels: list[str]
    properties: dict[str, Any]
    score: float = Field(default=1.0, ge=0.0)


class GraphRelationship(BaseModel):
    model_config = ConfigDict(frozen=True)

    rel_id: str
    rel_type: str
    source_id: str
    target_id: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphSearchRequest(BaseModel):
    query_text: str
    entity_types: list[str] = Field(default_factory=list)
    max_depth: int = Field(default=2, ge=1, le=5)
    limit: int = Field(default=20, ge=1, le=100)
    filters: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str = Field(default="", description="Tenant ID for multi-tenant isolation")


class GraphSearchResult(BaseModel):
    entities: list[GraphEntity]
    relationships: list[GraphRelationship]
    paths: list[list[str]] = Field(
        default_factory=list,
        description="Ordered node-id paths from query entity to related entities",
    )
    total_traversed: int


class GraphIngestRequest(BaseModel):
    """Upsert a batch of entities + relationships into the knowledge graph."""

    entities: list[GraphEntity]
    relationships: list[GraphRelationship] = Field(default_factory=list)
    source_uri: str | None = None


class GraphIngestResponse(BaseModel):
    nodes_created: int
    nodes_merged: int
    relationships_created: int
    job_id: UUID = Field(default_factory=uuid4)


class AsyncIngestResponse(BaseModel):
    """Returned immediately by POST /graph/ingest/async."""

    job_id: str
    status: str = "queued"
    entities_queued: int
    relationships_queued: int


class JobStatusResponse(BaseModel):
    """Returned by GET /graph/jobs/{job_id}."""

    job_id: str
    status: str
    nodes_merged: int
    rels_created: int
    error: str | None
    entities_queued: int
    relationships_queued: int
