"""Provenance Map schemas — full source-tracking for every AIM answer."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

# ── Python 3.12 type aliases ──────────────────────────────────────────────────
type SourceID = str
type EntityID = str
type Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class SourceType(StrEnum):
    NEO4J_GRAPH = "neo4j_graph"
    PINECONE_VECTOR = "pinecone_vector"
    SLACK_MCP = "slack_mcp"
    JIRA_MCP = "jira_mcp"
    LLM_SYNTHESIS = "llm_synthesis"


class CitationSpan(BaseModel):
    """Character-level span within the final answer that cites a source."""

    model_config = ConfigDict(frozen=True)

    start: int = Field(..., ge=0, description="Inclusive start char offset in answer")
    end: int = Field(..., ge=0, description="Exclusive end char offset in answer")
    text: str = Field(..., description="The verbatim text slice being cited")


class SourceReference(BaseModel):
    """A single source that contributed to the answer."""

    model_config = ConfigDict(frozen=True)

    source_id: SourceID = Field(default_factory=lambda: str(uuid4()))
    source_type: SourceType
    uri: str | None = Field(default=None, description="Deep-link to original document")
    title: str | None = None
    content_snippet: str = Field(..., description="The exact chunk retrieved")
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    confidence: Confidence = Field(..., description="Retrieval similarity score [0,1]")
    metadata: dict[str, Any] = Field(default_factory=dict)
    spans: list[CitationSpan] = Field(default_factory=list)


class GraphProvenanceNode(BaseModel):
    """A Neo4j entity that was traversed during reasoning."""

    model_config = ConfigDict(frozen=True)

    entity_id: EntityID
    entity_type: str
    labels: list[str]
    properties: dict[str, Any]
    relationship_path: list[str] = Field(
        default_factory=list,
        description="Ordered list of relationship types from query root to this node",
    )


class GraphProvenanceEdge(BaseModel):
    """A Neo4j relationship that was traversed during reasoning."""

    model_config = ConfigDict(frozen=True)

    source_entity_id: EntityID
    target_entity_id: EntityID
    rel_type: str
    # Stable identifier matching GraphRelationship.rel_id — the frontend uses
    # this to cross-reference ProvenanceMap.violating_edge_ids and colour
    # temporally inverted edges red.
    rel_id: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ResolvedEntity(BaseModel):
    """An entity that appears across multiple source types (cross-system resolution)."""

    model_config = ConfigDict(frozen=True)

    canonical_name: str
    source_ids: list[SourceID]
    source_types: list[SourceType]


class TemporalEvent(BaseModel):
    """A time-stamped evidence point for causal chain visualisation."""

    model_config = ConfigDict(frozen=True)

    source_id: SourceID
    timestamp: datetime
    summary: str
    source_type: SourceType


class InstitutionalFact(BaseModel):
    """A durable claim with governance and evidence metadata."""

    model_config = ConfigDict(frozen=True)

    fact_id: str
    statement: str
    subject_entity_id: EntityID
    predicate: str
    object_entity_id: EntityID
    confidence: Confidence = 0.8
    verification_status: str = "inferred"
    truth_status: str = "active"
    valid_from: str | None = None
    valid_until: str | None = None
    evidence_artifact_id: str | None = None
    evidence_uri: str | None = None
    support_source_ids: list[SourceID] = Field(default_factory=list)
    contradicts_fact_ids: list[str] = Field(default_factory=list)
    authority_score: Confidence = 0.5
    source_authority: str = "unknown"
    winning_fact_id: str | None = None
    superseded_by_fact_id: str | None = None
    resolution_reason: str = ""
    stale: bool = False


class SubQueryTrace(BaseModel):
    """Maps one decomposed sub-query to its retrieved sources."""

    model_config = ConfigDict(frozen=True)

    sub_query_id: str
    sub_query_text: str
    source_ids: list[SourceID]
    graph_node_ids: list[EntityID] = Field(default_factory=list)


class ProvenanceMap(BaseModel):
    """Complete, immutable provenance record for one AIM response."""

    model_config = ConfigDict(frozen=True)

    trace_id: UUID = Field(default_factory=uuid4)
    query_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # All sources indexed by source_id for O(1) look-ups
    sources: dict[SourceID, SourceReference] = Field(default_factory=dict)

    # Graph nodes traversed
    graph_nodes: list[GraphProvenanceNode] = Field(default_factory=list)

    # Graph relationships (edges) traversed — enables frontend 3D edge rendering
    graph_edges: list[GraphProvenanceEdge] = Field(default_factory=list)

    # Count of causal edges that failed timestamp direction integrity checks
    direction_violations: int = Field(default=0)

    # ``rel_id`` values of edges whose declared causal direction was
    # contradicted by timestamps — emitted so the 3D nebula can colour the
    # offenders red instead of just showing a faceless count.
    violating_edge_ids: list[str] = Field(default_factory=list)

    # Per sub-query source attribution
    sub_query_traces: list[SubQueryTrace] = Field(default_factory=list)

    # Answer segment → source IDs  (key = short hash of the text segment)
    citation_map: dict[str, list[SourceID]] = Field(default_factory=dict)

    # Character-level citation spans for precise UI highlighting
    citation_spans: list[CitationSpan] = Field(default_factory=list)

    # Cross-system entity resolution (same entity found in graph + vector + MCP)
    resolved_entities: list[ResolvedEntity] = Field(default_factory=list)

    # Chronological evidence chain for temporal/causal reasoning
    temporal_chain: list[TemporalEvent] = Field(default_factory=list)

    # Durable claims derived from traversed graph facts and relationships.
    institutional_facts: list[InstitutionalFact] = Field(default_factory=list)

    overall_confidence: Confidence = Field(..., description="Weighted aggregate [0,1]")
    reasoning_steps: list[str] = Field(default_factory=list)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def with_source(self, ref: SourceReference) -> "ProvenanceMap":
        return self.model_copy(
            update={"sources": {**self.sources, ref.source_id: ref}}
        )

    def with_graph_node(self, node: GraphProvenanceNode) -> "ProvenanceMap":
        return self.model_copy(update={"graph_nodes": [*self.graph_nodes, node]})

    @property
    def source_types_used(self) -> set[SourceType]:
        return {s.source_type for s in self.sources.values()}
