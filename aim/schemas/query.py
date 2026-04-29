"""Request / Response schemas for the /query endpoint."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from aim.schemas.provenance import ProvenanceMap


class ReasoningDepth(StrEnum):
    SHALLOW = "shallow"   # single-hop, fast
    STANDARD = "standard" # default multi-hop
    DEEP = "deep"         # exhaustive graph traversal


class MCPSources(BaseModel):
    """Which live MCP sources to pull context from."""

    slack: bool = True
    jira: bool = True
    slack_channels: list[str] = Field(default_factory=list)
    jira_projects: list[str] = Field(default_factory=list)


class CostInfo(BaseModel):
    """Token usage and estimated cost for a single query."""

    model_config = ConfigDict(frozen=True)

    # LLM tokens (decomposer + synthesizer combined)
    input_tokens: int = 0
    output_tokens: int = 0
    # Embedding tokens (OpenAI text-embedding-3-small)
    embedding_tokens: int = 0
    # Estimated cost in USD — based on public list prices, not invoiced cost.
    # Claude Opus 4.6: $15/1M input, $75/1M output
    # text-embedding-3-small: $0.02/1M tokens
    estimated_cost_usd: float = 0.0


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=4096)
    query_id: UUID = Field(default_factory=uuid4)
    # Optional thread_id links this query to an ongoing conversation.
    # If omitted, the query is stateless.
    thread_id: UUID | None = Field(
        default=None,
        description="Link to an existing conversation thread for multi-turn context.",
    )
    reasoning_depth: ReasoningDepth = ReasoningDepth.STANDARD
    mcp_sources: MCPSources = Field(default_factory=MCPSources)
    top_k: int = Field(default=10, ge=1, le=50)
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata filters forwarded to Pinecone and Neo4j",
    )
    stream: bool = Field(default=False, description="Stream the synthesis token-by-token")


class SubQueryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    sub_query_id: str
    sub_query_text: str
    graph_hits: int
    vector_hits: int
    mcp_hits: int


class QueryResponse(BaseModel):
    query_id: UUID
    thread_id: UUID | None = None
    original_query: str
    answer: str
    sub_query_results: list[SubQueryResult] = Field(default_factory=list)
    provenance: ProvenanceMap
    model_used: str
    latency_ms: float
    cost_info: CostInfo | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StreamChunk(BaseModel):
    """SSE payload during streaming synthesis."""

    model_config = ConfigDict(frozen=True)

    chunk_type: str  # "token" | "sub_query" | "citation" | "done" | "error"
    content: str
    query_id: UUID
    sequence: int
    request_id: str | None = None  # X-Request-ID for stream correlation
    # Populated only on the final "done" event
    thread_id: UUID | None = None
    sources: list[dict[str, Any]] | None = None
    confidence: float | None = None
    cost_info: CostInfo | None = None
    provenance: dict[str, Any] | None = None
