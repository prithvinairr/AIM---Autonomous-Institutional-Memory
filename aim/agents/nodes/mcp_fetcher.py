"""Node 4 — MCP Context Fetcher.

Pulls live context from Slack and Jira via the MCP handler,
running both providers concurrently.

MCP relevance scoring: instead of hardcoding ``confidence=0.85``,
computes actual relevance between the user query and each retrieved
chunk using token overlap + sequence similarity.
"""
from __future__ import annotations

import asyncio
from difflib import SequenceMatcher

import structlog

from aim.agents.state import AgentState
from aim.config import get_settings
from aim.mcp.handler import MCPHandler
from aim.schemas.mcp import MCPContext, MCPContextRequest, MCPProviderType
from aim.schemas.provenance import SourceReference, SourceType
from aim.utils.access_control import filter_sources_by_access, prune_source_map

log = structlog.get_logger(__name__)


def _compute_mcp_relevance(query: str, text: str) -> float:
    """Compute relevance between query and MCP text.

    Uses a blend of:
      - Token overlap (Jaccard-like coefficient)
      - Sequence similarity (SequenceMatcher ratio)
      - A base bonus (+0.3) since MCP items are fetched specifically
        for this query (not a random corpus)

    Returns a score in [0.0, 1.0].
    """
    query_lower = query.lower()
    text_lower = text.lower()

    query_tokens = set(query_lower.split())
    text_tokens = set(text_lower.split()[:100])

    if not query_tokens or not text_tokens:
        return 0.5

    # Token overlap (Jaccard coefficient)
    overlap = len(query_tokens & text_tokens) / len(query_tokens | text_tokens)

    # Sequence similarity (bounded to first 200 chars for performance)
    seq_sim = SequenceMatcher(
        None, query_lower[:200], text_lower[:200]
    ).ratio()

    # Blend: 60% token overlap + 40% sequence similarity + base bonus
    raw = 0.6 * overlap + 0.4 * seq_sim + 0.3
    return round(min(max(raw, 0.1), 1.0), 4)


async def fetch_mcp_context(state: AgentState) -> AgentState:
    settings = get_settings()
    steps = list(state.reasoning_steps)
    new_sources: dict[str, SourceReference] = dict(state.sources)
    sq_source_map: dict[str, list[str]] = {
        k: list(v) for k, v in state.sub_query_source_map.items()
    }

    # Determine which providers are active based on token configuration
    providers: list[MCPProviderType] = []
    if settings.slack_bot_token:
        providers.append(MCPProviderType.SLACK)
    if settings.jira_api_token:
        providers.append(MCPProviderType.JIRA)

    if not providers:
        steps.append("MCP fetch skipped: no providers configured.")
        return state.model_copy(update={"reasoning_steps": steps})

    request = MCPContextRequest(
        query_text=state.original_query,
        providers=providers,
        slack_channels=settings.slack_default_channels,
        jira_projects=settings.jira_default_projects,
        max_results_per_provider=5,
    )

    try:
        handler = MCPHandler()
        mcp_ctx: MCPContext = await handler.fetch(request)

        # Register each retrieved chunk as a provenance source with real relevance.
        # Each source is attributed to the sub-query it best answers, which
        # makes the returned provenance trace replayable instead of a flat
        # "live context was fetched" blob.
        mcp_source_ids: list[str] = []
        for uri, text in mcp_ctx.as_text_chunks():
            source_type = (
                SourceType.SLACK_MCP if "slack://" in uri else SourceType.JIRA_MCP
            )
            relevance = _compute_mcp_relevance(state.original_query, text)
            source_artifact_id = ""
            if uri:
                import hashlib
                source_artifact_id = "source:" + hashlib.sha256(uri.encode()).hexdigest()[:32]
            ref = SourceReference(
                source_type=source_type,
                uri=uri,
                content_snippet=text[:500],
                confidence=relevance,
                metadata={
                    "mcp_query": state.original_query,
                    "source_artifact_id": source_artifact_id,
                    "native_uri": uri,
                },
            )
            new_sources[ref.source_id] = ref
            mcp_source_ids.append(ref.source_id)
            best_sub_query = max(
                state.sub_queries or [state.original_query],
                key=lambda sq: _compute_mcp_relevance(sq, text),
            )
            existing = sq_source_map.get(best_sub_query, [])
            sq_source_map[best_sub_query] = existing + [ref.source_id]

        steps.append(
            f"MCP fetch: {mcp_ctx.total_items} items "
            f"({len(mcp_ctx.slack_contexts)} Slack channels, "
            f"{len(mcp_ctx.jira_contexts)} Jira projects)."
        )
        log.info("mcp_fetcher.done", total_items=mcp_ctx.total_items)

        if state.access_principals:
            new_sources = filter_sources_by_access(
                new_sources,
                principals=state.access_principals,
                tenant_id=state.tenant_id,
            )
            sq_source_map = prune_source_map(sq_source_map, set(new_sources))

        return state.model_copy(
            update={
                "mcp_context": mcp_ctx,
                "sources": new_sources,
                "sub_query_source_map": sq_source_map,
                "reasoning_steps": steps,
            }
        )

    except Exception as exc:
        log.error("mcp_fetcher.error", error=str(exc))
        steps.append(f"MCP fetch failed (non-fatal): {exc}")
        return state.model_copy(update={"reasoning_steps": steps})
