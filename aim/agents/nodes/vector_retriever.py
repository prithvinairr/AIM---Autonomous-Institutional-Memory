"""Node 3 — Vector Retriever.

Runs semantic similarity search against Pinecone for each sub-query.

Retrieval strategy
──────────────────
1. Batch-embed all sub-queries in a single OpenAI API call (``batch_embed``).
2. Fan out all Pinecone queries in parallel (``asyncio.gather``).
3. De-duplicate matches by vector ID across sub-queries.
4. Tracks per-sub-query source attribution in ``state.sub_query_source_map``.

This replaces the previous serial-per-sub-query loop which made N separate
OpenAI embedding calls and N sequential Pinecone queries.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from aim.agents.state import AgentState
from aim.config import get_settings
from aim.schemas.provenance import SourceReference, SourceType
from aim.utils.access_control import (
    filter_sources_by_access,
    filter_vector_snippets_by_access,
    prune_source_map,
)
from aim.utils.circuit_breaker import CircuitOpenError, get_breaker
from aim.utils.metrics import NODE_ERRORS
from aim.vectordb import get_vectordb_provider
from aim.vectordb.base import VectorDBProvider
from aim.vectordb.pinecone_client import PineconeClient

log = structlog.get_logger(__name__)


async def _query_one(
    sub_q: str,
    embedding: list[float],
    provider: VectorDBProvider,
    top_k: int,
    score_threshold: float,
    filters: dict[str, Any] | None,
    node_timeout: float,
) -> tuple[str, list[dict[str, Any]]]:
    """Run a single vector query, returning (sub_query, matches)."""
    breaker = get_breaker("pinecone")
    try:
        async with asyncio.timeout(node_timeout):
            matches = await breaker.call(
                provider.query,
                embedding,
                top_k=top_k,
                score_threshold=score_threshold,
                filters=filters,
            )
        return sub_q, matches
    except (CircuitOpenError, asyncio.TimeoutError) as exc:
        log.warning(
            "vector_retriever.sub_query_skipped",
            sub_q=sub_q[:60],
            reason=type(exc).__name__,
        )
        return sub_q, []


async def retrieve_vectors(state: AgentState) -> AgentState:
    if not state.sub_queries:
        log.warning("vector_retriever.no_sub_queries")
        return state

    # Per-branch modality gate (γ.3). When the branch orchestrator spawns a
    # graph-only recipe, this node is a no-op — the fusion wrapper still
    # runs but has nothing to fuse, which is the intended degenerate case.
    if not state.vector_search_enabled:
        log.info("vector_retriever.skipped_by_branch")
        return state.model_copy(update={
            "reasoning_steps": [*state.reasoning_steps, "Vector search skipped (branch modality=graph-only)."],
        })

    settings = get_settings()
    breaker = get_breaker("pinecone")
    vdb = get_vectordb_provider()
    from aim.llm import get_embedding_provider
    embedder = get_embedding_provider()
    t_node = time.perf_counter()

    all_snippets: list[dict[str, Any]] = list(state.vector_snippets)
    new_sources: dict[str, SourceReference] = dict(state.sources)
    sq_source_map: dict[str, list[str]] = {k: list(v) for k, v in state.sub_query_source_map.items()}
    steps = list(state.reasoning_steps)
    seen_ids: set[str] = {s["id"] for s in all_snippets if "id" in s}

    try:
        # ── Step 1: batch-embed all sub-queries (single OpenAI call) ──────────
        embed_tokens = 0
        try:
            embeddings, embed_tokens = await breaker.call(
                embedder.embed_batch, state.sub_queries
            )
        except CircuitOpenError:
            log.warning("vector_retriever.circuit_open", phase="embed")
            steps.append("Vector search skipped (Pinecone circuit open).")
            return state.model_copy(update={"reasoning_steps": steps})

        # ── Step 2: fan out Pinecone queries in parallel ───────────────────────
        query_results: list[tuple[str, list[dict[str, Any]]]] = await asyncio.gather(*[
            _query_one(
                sub_q=sq,
                embedding=emb,
                provider=vdb,
                top_k=settings.top_k_vectors,
                score_threshold=settings.similarity_threshold,
                filters=state.vector_filters or None,
                node_timeout=settings.node_timeout_seconds,
            )
            for sq, emb in zip(state.sub_queries, embeddings)
        ])

        # ── Step 3: merge results, de-duplicate by vector ID ──────────────────
        failed_sub_queries = 0
        for sub_q, matches in query_results:
            if not matches:
                failed_sub_queries += 1
            sq_new_ids: list[str] = []

            for match in matches:
                vec_id: str = match["id"]
                if vec_id in seen_ids:
                    continue
                seen_ids.add(vec_id)

                meta: dict[str, Any] = match.get("metadata", {})
                score: float = float(match.get("score", 0.0))
                text: str = meta.get("text", "")

                all_snippets.append({"id": vec_id, "text": text, "score": score, **meta})

                ref = SourceReference(
                    source_type=SourceType.PINECONE_VECTOR,
                    uri=meta.get("source_url"),
                    title=meta.get("title"),
                    content_snippet=text[:500],
                    confidence=min(max(score, 0.0), 1.0),
                    metadata={"vector_id": vec_id, "sub_query": sub_q},
                )
                new_sources[ref.source_id] = ref
                sq_new_ids.append(ref.source_id)

            existing = sq_source_map.get(sub_q, [])
            sq_source_map[sub_q] = existing + sq_new_ids

        total_sq = len(state.sub_queries)
        succeeded = total_sq - failed_sub_queries
        steps.append(
            f"Vector search: {len(all_snippets)} unique snippets across "
            f"{total_sq} sub-queries (parallel)."
        )
        if failed_sub_queries > 0:
            steps.append(
                f"Partial vector results: {failed_sub_queries}/{total_sq} "
                f"sub-queries returned no results (circuit open or timeout)."
            )
            log.warning(
                "vector_retriever.partial_results",
                succeeded=succeeded,
                failed=failed_sub_queries,
                total=total_sq,
            )
        log.info(
            "vector_retriever.done",
            snippets=len(all_snippets),
            sub_queries=total_sq,
        )

    except Exception as exc:
        NODE_ERRORS.labels(node_name="vector_retriever", error_type=type(exc).__name__).inc()
        log.error("vector_retriever.error", error=str(exc))
        steps.append(f"Vector retrieval failed (non-fatal): {exc}")
    finally:
        # NODE_LATENCY is already recorded by the _timed_node wrapper in reasoning_agent.py;
        # do not observe it here to avoid double-counting.
        pass

    if state.access_principals:
        all_snippets = filter_vector_snippets_by_access(
            all_snippets,
            principals=state.access_principals,
            tenant_id=state.tenant_id,
        )
        new_sources = filter_sources_by_access(
            new_sources,
            principals=state.access_principals,
            tenant_id=state.tenant_id,
        )
        sq_source_map = prune_source_map(sq_source_map, set(new_sources))

    return state.model_copy(
        update={
            "vector_snippets": all_snippets,
            "sources": new_sources,
            "sub_query_source_map": sq_source_map,
            "reasoning_steps": steps,
            "embedding_tokens": state.embedding_tokens + embed_tokens,
        }
    )
