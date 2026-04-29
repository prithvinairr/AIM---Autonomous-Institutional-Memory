"""LangGraph agent state definition for the AIM Reasoning Agent."""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from aim.schemas.graph import GraphEntity, GraphRelationship
from aim.schemas.mcp import MCPContext
from aim.schemas.provenance import ProvenanceMap, SourceReference
from aim.schemas.query import ReasoningDepth


def _is_zero(v: Any) -> bool:
    """LangGraph's pydantic adapter initializes channels with the type's
    zero value (``False`` for bool, ``""`` for str, ``[]`` for list,
    ``{}`` for dict, ``None`` for Optional). Reducers must treat these
    as 'channel never written' or the initial state's real value gets
    discarded as soon as it's reduced against the default.
    """
    if v is None:
        return True
    if v is False:
        return True
    if isinstance(v, (str, list, dict, tuple, set)) and len(v) == 0:
        return True
    return False


def _keep_first(left: Any, right: Any) -> Any:
    """LangGraph reducer: identity fields never change after the first
    real write. Channel default (zero-value) on either side is treated
    as 'unset', so the populated value wins. When both are populated,
    left (first writer) wins — this is what makes immutable identity
    fields stable across parallel fan-out.
    """
    if _is_zero(left):
        return right
    if _is_zero(right):
        return left
    return left


def _prefer_populated(left: Any, right: Any) -> Any:
    """LangGraph reducer for fields that *one* parallel branch may
    update while the other passes through unchanged. We prefer the
    populated value over the empty default. Equal values collapse
    cleanly; if both branches diverge non-trivially, the right (later)
    write wins — a deterministic last-writer policy.

    "Empty" means: ``None``, ``""``, ``[]``, ``{}``, ``False`` for
    bools we treat as flags, and ``0`` for counters that we don't want
    to silently overwrite.
    """
    if left == right:
        return left
    if _is_zero(right):
        return left
    if _is_zero(left):
        return right
    # Both populated and different — last writer wins.
    return right


def _latest_value(left: Any, right: Any) -> Any:
    """Reducer for control fields where ``False`` is a real write.

    ``_prefer_populated`` deliberately treats ``False`` as empty for data
    fields, but loop-control flags must be able to transition from
    ``True`` back to ``False``. Otherwise a single failed evaluation traps
    the graph in a reloop until LangGraph's recursion limit is hit.
    """
    return right


class AgentState(BaseModel):
    """Immutable-compatible state threaded through all LangGraph nodes.

    Use ``model_copy(update={...})`` to produce the next state — never mutate in place.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    # Annotated with a reducer because the LangGraph topology fans these
    # values through parallel nodes (search_graph || fetch_mcp) which
    # both echo the identity fields back at the join. Without a reducer
    # LangGraph rejects the concurrent write.
    query_id: Annotated[UUID, _keep_first]
    original_query: Annotated[str, _keep_first]
    reasoning_depth: Annotated[ReasoningDepth, _keep_first] = ReasoningDepth.STANDARD

    # ── Multi-tenancy ────────────────────────────────────────────────────────
    # Derived from API key hash when multi_tenant mode is enabled.
    # All graph queries are scoped to this tenant. Annotated with the
    # keep-first reducer for the same parallel-pass-through reason as
    # the identity fields above.
    tenant_id: Annotated[str, _keep_first] = ""

    # Principal identifiers allowed to see retrieved evidence. The route
    # derives these from trusted request context rather than user-provided
    # query filters, so graph/vector results can be pruned before synthesis.
    access_principals: Annotated[list[str], _keep_first] = Field(default_factory=list)

    # ── Conversation context ──────────────────────────────────────────────────
    # Optional thread for multi-turn conversations.
    thread_id: Annotated[UUID | None, _keep_first] = None
    # Prior turns as [{"role": "user", "content": "..."}, {"role": "assistant", ...}, ...]
    # Injected by the route handler from ConversationStore before the graph runs.
    conversation_history: Annotated[list[dict[str, str]], _keep_first] = Field(default_factory=list)

    # ── Decomposition ─────────────────────────────────────────────────────────
    # Written by decompose; read-only-passthrough afterward across both
    # parallel branches.
    sub_queries: Annotated[list[str], _prefer_populated] = Field(default_factory=list)

    # ── Graph search results ──────────────────────────────────────────────────
    graph_entities: Annotated[list[GraphEntity], _prefer_populated] = Field(default_factory=list)
    graph_relationships: Annotated[list[GraphRelationship], _prefer_populated] = Field(default_factory=list)

    # ── Vector search results — list of {id, text, score, ...metadata} ───────
    vector_snippets: Annotated[list[dict[str, Any]], _prefer_populated] = Field(default_factory=list)

    # Optional Pinecone metadata filters forwarded from the API request
    vector_filters: Annotated[dict[str, Any] | None, _keep_first] = None

    # ── MCP live context ──────────────────────────────────────────────────────
    mcp_context: Annotated[MCPContext | None, _prefer_populated] = None

    # ── Per-sub-query source attribution ─────────────────────────────────────
    sub_query_source_map: Annotated[dict[str, list[str]], _prefer_populated] = Field(default_factory=dict)

    # ── Provenance accumulator ────────────────────────────────────────────────
    sources: Annotated[dict[str, SourceReference], _prefer_populated] = Field(default_factory=dict)

    # ── Synthesis output ──────────────────────────────────────────────────────
    answer: Annotated[str, _prefer_populated] = ""
    reasoning_steps: Annotated[list[str], _prefer_populated] = Field(default_factory=list)
    citation_map: Annotated[dict[str, list[str]], _prefer_populated] = Field(default_factory=dict)
    provenance: Annotated[ProvenanceMap | None, _prefer_populated] = None

    # ── Token usage tracking ──────────────────────────────────────────────────
    input_tokens: Annotated[int, _prefer_populated] = 0
    output_tokens: Annotated[int, _prefer_populated] = 0
    embedding_tokens: Annotated[int, _prefer_populated] = 0

    # ── Evaluation & reasoning loop ─────────────────────────────────────────
    evaluation_score: Annotated[float, _prefer_populated] = 0.0
    evaluation_feedback: Annotated[str, _prefer_populated] = ""
    needs_reloop: Annotated[bool, _latest_value] = False
    loop_count: Annotated[int, _prefer_populated] = 0

    # ── Strategy-aware re-planning ────────────────────────────────────────────
    retrieval_strategy: Annotated[str, _prefer_populated] = "balanced"
    failed_strategies: Annotated[list[str], _prefer_populated] = Field(default_factory=list)

    # ── Graph intelligence ───────────────────────────────────────────────────
    query_intent: Annotated[str, _prefer_populated] = "general"
    entity_pairs: Annotated[list[list[str]], _prefer_populated] = Field(default_factory=list)
    path_results: Annotated[list[dict[str, Any]], _prefer_populated] = Field(default_factory=list)
    is_multi_hop: Annotated[bool, _prefer_populated] = False
    missing_hops: Annotated[list[str], _prefer_populated] = Field(default_factory=list)

    # ── Data sovereignty ─────────────────────────────────────────────────────
    source_classifications: Annotated[dict[str, str], _prefer_populated] = Field(default_factory=dict)
    redacted_fields: Annotated[dict[str, list[str]], _prefer_populated] = Field(default_factory=dict)
    sovereignty_audit: Annotated[list[dict[str, Any]], _prefer_populated] = Field(default_factory=list)

    # ── Retrieval fusion override ────────────────────────────────────────────
    fusion_mode_override: Annotated[str | None, _keep_first] = None

    # ── Per-branch modality toggles ──────────────────────────────────────────
    graph_search_enabled: Annotated[bool, _keep_first] = True
    vector_search_enabled: Annotated[bool, _keep_first] = True

    # ── Control ───────────────────────────────────────────────────────────────
    error: Annotated[str | None, _prefer_populated] = None
    retries: Annotated[int, _prefer_populated] = 0

    model_config = ConfigDict(arbitrary_types_allowed=True, use_enum_values=False)
