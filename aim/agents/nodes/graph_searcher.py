"""Node 2 — Knowledge Graph Searcher.

For each sub-query, searches Neo4j for matching entities and their
neighbourhood. Tracks which sources answer which sub-query.

A+ upgrades:
- Hybrid (fulltext + vector) entity retrieval activates the dormant
  ``entity_embedding_idx``.
- Relationship properties (e.g. ``mechanism``, ``context``) are emitted as
  first-class SourceReference objects so causal explanations are preserved.
- Proactive path-finding between top-ranked entity pairs (not just those
  the decomposer extracts) surfaces causal chains automatically.
"""
from __future__ import annotations

import asyncio
import re
import time

import structlog

from aim.agents.state import AgentState
from aim.config import get_settings
from aim.graph.neo4j_client import Neo4jClient
from aim.llm import get_embedding_provider
from aim.schemas.graph import GraphEntity, GraphRelationship
from aim.schemas.provenance import SourceReference, SourceType
from aim.schemas.query import ReasoningDepth
from aim.utils.access_control import (
    filter_graph_by_access,
    filter_sources_by_access,
    prune_source_map,
)
from aim.utils.circuit_breaker import CircuitOpenError, get_breaker
from aim.utils.metrics import NEO4J_QUERY_LATENCY, NEO4J_RESULTS, NODE_ERRORS

log = structlog.get_logger(__name__)

_EXACT_IDENTIFIER_RE = re.compile(
    r"\b[A-Z][A-Z0-9]{1,12}-(?:\d{2,6})(?:-\d{1,6})?\b"
)

# Intent → apoc relationship filter mapping.
# Empty string means both directions (bidirectional).
# Trailing '>' restricts to outgoing only.
_INTENT_REL_FILTERS: dict[str, str] = {
    "ownership":   "OWNS|MANAGES|LEADS|MEMBER_OF|LEADS_PROJECT",   # bidirectional
    "dependency":  "DEPENDS_ON|USED_IN|PART_OF|REFERENCES>",       # outgoing only
    "incident":    "RESPONDED_TO|IMPACTED|CAUSED_BY|LED_TO",       # bidirectional
    "decision":    "PROPOSED_BY|APPROVED_BY|AFFECTS|SUPERSEDES|LED_TO",  # bidirectional
    "temporal":    "LED_TO|CAUSED_BY|SUPERSEDES",                  # bidirectional
    "general":     "",                                              # all directions
}

# Relationship-type weights used for path-ranking. Causal/temporal edges
# dominate; ownership is strong; generic references are low-signal.
_REL_TYPE_WEIGHTS: dict[str, float] = {
    "CAUSED_BY": 1.00,
    "LED_TO": 1.00,
    "SUPERSEDES": 0.95,
    "APPROVED_BY": 0.90,
    "PROPOSED_BY": 0.85,
    "OWNS": 0.80,
    "MANAGES": 0.75,
    "DEPENDS_ON": 0.75,
    "MEMBER_OF": 0.70,
    "AFFECTS": 0.65,
    "IMPACTED": 0.65,
    "RESPONDED_TO": 0.65,
    "REFERENCES": 0.50,
}

# ── Feedback-adjusted weights ────────────────────────────────────────────────
# Blend static priors with learned signals from user feedback. When a causal
# edge source was marked "helpful", its rel_type weight nudges up — so the
# system learns from human signals instead of relying purely on hand-tuned
# constants.  Weight is stored in Redis under aim:rel_weights:{rel_type}.
_FEEDBACK_BOOST_PER_SIGNAL = 0.03
_FEEDBACK_WEIGHT_FLOOR = 0.30
_FEEDBACK_WEIGHT_CAP = 1.00


async def _load_feedback_weights() -> dict[str, float]:
    """Async version: read the feedback weight hash from Redis."""
    base = dict(_REL_TYPE_WEIGHTS)
    try:
        from aim.utils.cache import get_response_cache
        cache = get_response_cache()
        if not getattr(cache, "_redis_ok", False):
            return base
        raw = await cache._redis.hgetall("aim:rel_weight_adj")
        if raw:
            for rel_type, delta_str in raw.items():
                key = rel_type.decode() if isinstance(rel_type, bytes) else str(rel_type)
                try:
                    delta = float(delta_str)
                except (ValueError, TypeError):
                    continue
                if key in base:
                    base[key] = max(
                        _FEEDBACK_WEIGHT_FLOOR,
                        min(_FEEDBACK_WEIGHT_CAP, base[key] + delta),
                    )
    except Exception:
        pass
    return base


def _extract_exact_identifiers(texts: list[str]) -> list[str]:
    """Pull ticket/incident-style IDs that should anchor graph retrieval."""
    seen: set[str] = set()
    identifiers: list[str] = []
    for text in texts:
        for match in _EXACT_IDENTIFIER_RE.findall(text or ""):
            if match in seen:
                continue
            seen.add(match)
            identifiers.append(match)
    return identifiers


_TEACHER_BFS_QUERY = """
MATCH (seed:Entity {aim_id: $seed_id})
CALL {
    WITH seed
    MATCH path = (seed)-[*1..2]-(n:Entity)
    RETURN nodes(path) AS ns
    LIMIT $limit
}
WITH collect(ns) AS all_nodes
RETURN all_nodes
"""


async def _fetch_teacher_bfs_candidates(
    client: Neo4jClient,
    *,
    seed_id: str,
    limit: int,
    timeout_seconds: float,
) -> list[GraphEntity]:
    """Return a small graph-only BFS candidate set from the strongest seed.

    This is intentionally used as a *candidate teacher*, not as the whole
    retrieval result. Normal hybrid graph/vector retrieval still runs first;
    the BFS set only improves multi-hop top-10 density when the graph contains
    useful nearby bridge nodes.
    """
    teacher_nodes: list[GraphEntity] = []
    seen_teacher_ids: set[str] = set()
    async with asyncio.timeout(timeout_seconds):
        async with client._driver.session(database=client._database) as session:
            result = await session.run(
                _TEACHER_BFS_QUERY,
                seed_id=seed_id,
                limit=limit,
            )
            async for record in result:
                for ns in record["all_nodes"] or []:
                    for node in ns:
                        aim_id = node.get("aim_id") or str(node.element_id)
                        if aim_id in seen_teacher_ids:
                            continue
                        seen_teacher_ids.add(aim_id)
                        teacher_nodes.append(
                            GraphEntity(
                                entity_id=aim_id,
                                labels=list(getattr(node, "labels", []) or []),
                                properties=dict(node),
                                score=max(0.6, 1.25 - (len(teacher_nodes) * 0.03)),
                            )
                        )
    return teacher_nodes


def _source_reference_for_entity(
    entity: GraphEntity,
    *,
    teacher_bfs: bool = False,
) -> SourceReference:
    snippet = (
        f"{', '.join(entity.labels)}: "
        + ", ".join(f"{k}={v}" for k, v in list(entity.properties.items())[:6])
    )
    metadata = {"entity_id": entity.entity_id, "labels": entity.labels}
    if teacher_bfs:
        metadata["teacher_bfs"] = True
    return SourceReference(
        source_type=SourceType.NEO4J_GRAPH,
        uri=f"neo4j://node/{entity.entity_id}",
        title=str(entity.properties.get("name", entity.entity_id)),
        content_snippet=snippet,
        confidence=min(max(float(entity.score), 0.0), 1.0),
        metadata=metadata,
    )


def _merge_teacher_bfs_candidates(
    entities: list[GraphEntity],
    sources: dict[str, SourceReference],
    seen_ids: set[str],
    teacher_nodes: list[GraphEntity],
) -> list[GraphEntity]:
    """Boost existing entities and append new teacher candidates, then sort."""
    if not teacher_nodes:
        return entities

    teacher_scores = {node.entity_id: node.score for node in teacher_nodes}
    teacher_by_id = {node.entity_id: node for node in teacher_nodes}
    rebuilt_entities: list[GraphEntity] = []
    for entity in entities:
        teacher_score = teacher_scores.pop(entity.entity_id, None)
        if teacher_score is None:
            rebuilt_entities.append(entity)
            continue
        rebuilt_entities.append(
            entity.model_copy(
                update={"score": float(entity.score or 0.0) + teacher_score}
            )
        )

    for entity_id in list(teacher_scores):
        entity = teacher_by_id[entity_id]
        rebuilt_entities.append(entity)
        ref = _source_reference_for_entity(entity, teacher_bfs=True)
        sources[ref.source_id] = ref
        seen_ids.add(entity.entity_id)

    return sorted(rebuilt_entities, key=lambda x: x.score, reverse=True)


def _rel_source_snippet(rel: GraphRelationship, names: dict[str, str]) -> str | None:
    """If a relationship carries causal metadata, produce a human-readable
    snippet that captures the explanation, suitable for first-class citation.
    """
    props = rel.properties or {}
    explanation = (
        props.get("mechanism")
        or props.get("context")
        or props.get("reason")
        or props.get("evidence_uri")
        or props.get("source_uri")
    )
    if not explanation:
        return None
    a = names.get(rel.source_id, rel.source_id)
    b = names.get(rel.target_id, rel.target_id)
    return f"{a} —[{rel.rel_type}]→ {b}: {explanation}"


async def search_knowledge_graph(state: AgentState) -> AgentState:
    log.info(
        "graph_searcher.entry",
        graph_search_enabled=state.graph_search_enabled,
        sub_queries=len(state.sub_queries),
        retrieval_strategy=state.retrieval_strategy,
    )
    if not state.sub_queries:
        log.warning("graph_searcher.no_sub_queries")
        return state

    # Per-branch modality gate (γ.3). When the branch orchestrator spawns a
    # vector-only recipe, this node is a no-op — we still return a valid
    # state so the downstream join in the compiled graph fires cleanly.
    if not state.graph_search_enabled:
        log.info("graph_searcher.skipped_by_branch")
        return state.model_copy(
            update={
                "reasoning_steps": [
                    *state.reasoning_steps,
                    "Graph search skipped (branch modality=vector-only).",
                ],
            }
        )

    settings = get_settings()
    breaker = get_breaker("neo4j")

    # Depth and result limits by reasoning mode:
    #   SHALLOW — 1-hop, 5 entities, first sub-query only.
    #   STANDARD — configured depth (default 2), up to 20 entities per sub-query.
    #   DEEP    — 2× configured depth (capped at 5), up to 40 entities per sub-query.
    if state.reasoning_depth == ReasoningDepth.SHALLOW:
        search_depth = 1
        search_limit = 5
        sub_queries_to_run = state.sub_queries[:1]
    elif state.reasoning_depth == ReasoningDepth.DEEP:
        search_depth = min(settings.graph_search_depth * 2, 5)
        search_limit = 40
        sub_queries_to_run = state.sub_queries
    else:
        search_depth = settings.graph_search_depth
        search_limit = 20
        sub_queries_to_run = state.sub_queries

    rel_filter = _INTENT_REL_FILTERS.get(state.query_intent, "")
    max_degree = settings.graph_hub_degree_limit

    log.info(
        "graph_searcher.start",
        depth=state.reasoning_depth,
        search_depth=search_depth,
        sub_queries=len(sub_queries_to_run),
        intent=state.query_intent,
        rel_filter=rel_filter or "(bidirectional)",
        hub_degree_limit=max_degree,
    )

    all_entities: list[GraphEntity] = list(state.graph_entities)
    all_relationships: list[GraphRelationship] = list(state.graph_relationships)
    new_sources: dict[str, SourceReference] = dict(state.sources)
    sq_source_map: dict[str, list[str]] = {
        k: list(v) for k, v in state.sub_query_source_map.items()
    }
    steps = list(state.reasoning_steps)
    seen_ids: set[str] = {e.entity_id for e in all_entities}
    client = Neo4jClient()

    use_dampened = state.reasoning_depth != ReasoningDepth.SHALLOW
    # Hybrid search is used for STANDARD/DEEP; SHALLOW stays fulltext-only for speed.
    use_hybrid = use_dampened and settings.graph_use_hybrid_search

    # Precompute embeddings per sub-query for hybrid search. Batched for efficiency.
    sq_embeddings: dict[str, list[float]] = {}
    if use_hybrid:
        try:
            embedder = get_embedding_provider()
            embeddings, _tokens = await embedder.embed_batch(list(sub_queries_to_run))
            for sq, emb in zip(sub_queries_to_run, embeddings):
                sq_embeddings[sq] = emb
        except Exception as exc:
            log.warning("graph_searcher.embedding_failed", error=str(exc))
            use_hybrid = False

    async def _search_one_subquery(sub_q: str):
        t_q = time.perf_counter()
        try:
            async with asyncio.timeout(settings.node_timeout_seconds):
                if use_hybrid and sub_q in sq_embeddings:
                    result = await breaker.call(
                        client.search_hybrid,
                        query_text=sub_q,
                        embedding=sq_embeddings[sub_q],
                        max_depth=search_depth,
                        limit=search_limit,
                        rel_filter=rel_filter,
                        max_degree=max_degree,
                        tenant_id=state.tenant_id,
                    )
                elif use_dampened:
                    result = await breaker.call(
                        client.search_dampened,
                        query_text=sub_q,
                        max_depth=search_depth,
                        limit=search_limit,
                        rel_filter=rel_filter,
                        max_degree=max_degree,
                        tenant_id=state.tenant_id,
                    )
                else:
                    result = await breaker.call(
                        client.search_filtered,
                        query_text=sub_q,
                        max_depth=search_depth,
                        limit=search_limit,
                        rel_filter=rel_filter or ">",
                        tenant_id=state.tenant_id,
                    )
        except CircuitOpenError:
            log.warning("graph_searcher.circuit_open", sub_q=sub_q[:60])
            return sub_q, None, "circuit_open"
        except asyncio.TimeoutError:
            log.error(
                "graph_searcher.timeout",
                sub_q=sub_q[:60],
                timeout=settings.node_timeout_seconds,
            )
            NODE_ERRORS.labels(node_name="graph_searcher", error_type="timeout").inc()
            return sub_q, None, "timeout"

        NEO4J_QUERY_LATENCY.observe(time.perf_counter() - t_q)
        NEO4J_RESULTS.observe(len(result.entities))
        return sub_q, result, None

    def _record_graph_result(
        sub_q: str,
        result,
        *,
        prepend_entities: bool = False,
    ) -> int:
        sq_new_source_ids: list[str] = []
        new_entities: list[GraphEntity] = []

        for entity in result.entities:
            if entity.entity_id not in seen_ids:
                if prepend_entities:
                    new_entities.append(entity)
                else:
                    all_entities.append(entity)
                seen_ids.add(entity.entity_id)

        if new_entities:
            all_entities[:0] = new_entities

        all_relationships.extend(result.relationships)

        for entity in result.entities:
            snippet = (
                f"{', '.join(entity.labels)}: "
                + ", ".join(f"{k}={v}" for k, v in list(entity.properties.items())[:6])
            )
            ref = SourceReference(
                source_type=SourceType.NEO4J_GRAPH,
                uri=f"neo4j://node/{entity.entity_id}",
                title=str(entity.properties.get("name", entity.entity_id)),
                content_snippet=snippet,
                confidence=min(max(float(entity.score), 0.0), 1.0),
                metadata={"entity_id": entity.entity_id, "labels": entity.labels},
            )
            new_sources[ref.source_id] = ref
            sq_new_source_ids.append(ref.source_id)

        existing = sq_source_map.get(sub_q, [])
        sq_source_map[sub_q] = existing + sq_new_source_ids
        return len(sq_new_source_ids)

    exact_identifiers = _extract_exact_identifiers(
        [state.original_query, *sub_queries_to_run]
    )
    # exact_only_mode used to skip hybrid entirely when an ID was present.
    # That short-circuit caused false-empty retrieval whenever the exact
    # name lookup failed (e.g. user types "INC-2025-015" but entity is
    # named "INC-2025-015: Payment Double-Charge"). Now exact-anchor is
    # ADDITIVE: hybrid always runs, exact-anchor prepends extra hits.
    exact_only_mode = False

    try:
        search_results = []
        if not exact_only_mode:
            search_results = await asyncio.gather(
                *[_search_one_subquery(sq) for sq in sub_queries_to_run]
            )

        for sub_q, result, error in search_results:
            if error == "circuit_open":
                steps.append("Graph search skipped (circuit open).")
                break
            if error == "timeout":
                steps.append(f"Graph search timed out for: {sub_q[:60]}")
                continue
            if result is None:
                continue

            _record_graph_result(sub_q, result)

        anchored_sources = 0
        for identifier in exact_identifiers[:5]:
            try:
                async with asyncio.timeout(settings.node_timeout_seconds):
                    result = await breaker.call(
                        client.search_exact_name,
                        name=identifier,
                        limit=5,
                        rel_limit=30,
                        tenant_id=state.tenant_id,
                    )
                anchored_sources += _record_graph_result(
                    identifier,
                    result,
                    prepend_entities=True,
                )
            except (CircuitOpenError, asyncio.TimeoutError):
                steps.append(f"Exact identifier anchoring timed out for: {identifier}")
            except Exception as exc:
                log.warning(
                    "graph_searcher.exact_identifier_anchor_failed",
                    identifier=identifier,
                    error=str(exc),
                )
        if exact_identifiers:
            steps.append(
                f"Exact identifier anchoring: {len(exact_identifiers[:5])} "
                f"identifier(s), {anchored_sources} source(s)."
            )

        if (
            getattr(settings, "graph_teacher_bfs_enabled", True)
            and state.is_multi_hop
            and all_entities
        ):
            try:
                seed_id = all_entities[0].entity_id
                teacher_limit = int(getattr(settings, "graph_teacher_bfs_limit", 20))
                teacher_nodes = await _fetch_teacher_bfs_candidates(
                    client,
                    seed_id=seed_id,
                    limit=teacher_limit,
                    timeout_seconds=settings.node_timeout_seconds,
                )
                if teacher_nodes:
                    all_entities = _merge_teacher_bfs_candidates(
                        all_entities,
                        new_sources,
                        seen_ids,
                        teacher_nodes,
                    )
                    steps.append(
                        f"Teacher BFS boosted multi-hop candidates from seed {seed_id} "
                        f"({len(teacher_nodes)} node(s))."
                    )
            except Exception as exc:
                log.warning("graph_searcher.teacher_bfs_failed", error=str(exc))


        steps.append(
            f"Graph search: {len(all_entities)} entities, "
            f"{len(all_relationships)} relationships "
            f"(mode={'exact' if exact_only_mode else ('hybrid' if use_hybrid else 'fulltext')})."
        )
        log.info(
            "graph_searcher.done",
            entities=len(all_entities),
            rels=len(all_relationships),
            mode="exact" if exact_only_mode else ("hybrid" if use_hybrid else "fulltext"),
        )

    except Exception as exc:
        NODE_ERRORS.labels(node_name="graph_searcher", error_type=type(exc).__name__).inc()
        log.error("graph_searcher.error", error=str(exc))
        steps.append(f"Graph search failed (non-fatal): {exc}")
    finally:
        await client.close()

    # ── Causal relationship extraction ──────────────────────────────────────
    # Emit relationships carrying causal metadata (mechanism/context/reason) as
    # first-class SourceReference objects. This lets the synthesizer cite the
    # MECHANISM that explains WHY an event happened, not just the fact that
    # two entities are connected.
    entity_names: dict[str, str] = {
        e.entity_id: str(e.properties.get("name", e.entity_id))
        for e in all_entities
    }
    causal_rel_types = {"CAUSED_BY", "LED_TO", "SUPERSEDES", "AFFECTS", "IMPACTED"}
    causal_count = 0

    # Temporal decay: causal edges from more than _DECAY_HALF_LIFE_DAYS ago
    # have reduced confidence.  This prevents stale causal chains from 2019
    # from carrying the same weight as last week's incident.
    import math
    from datetime import datetime, timezone
    _DECAY_HALF_LIFE_DAYS = 180  # 6 months
    _now = datetime.now(timezone.utc)

    def _temporal_confidence(rel_props: dict) -> float:
        """Compute confidence for a causal edge with optional temporal decay."""
        base = 0.95
        ts_raw = rel_props.get("created_at") or rel_props.get("since") or rel_props.get("timestamp")
        if not ts_raw:
            return base
        try:
            if isinstance(ts_raw, str):
                # Handle partial dates like "2024-03"
                if len(ts_raw) <= 7:
                    ts_raw = ts_raw + "-01"
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            elif isinstance(ts_raw, datetime):
                ts = ts_raw
            else:
                return base
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            days_old = max((_now - ts).days, 0)
            decay = math.exp(-0.693 * days_old / _DECAY_HALF_LIFE_DAYS)
            return round(max(base * decay, 0.40), 4)
        except (ValueError, TypeError):
            return base

    for rel in all_relationships:
        if rel.rel_type not in causal_rel_types:
            continue
        snippet = _rel_source_snippet(rel, entity_names)
        if not snippet:
            continue
        confidence = _temporal_confidence(rel.properties or {})
        ref = SourceReference(
            source_type=SourceType.NEO4J_GRAPH,
            uri=f"neo4j://rel/{rel.rel_id}",
            title=(
                f"{rel.rel_type}: {entity_names.get(rel.source_id, '?')} -> "
                f"{entity_names.get(rel.target_id, '?')}"
            ),
            content_snippet=snippet,
            confidence=confidence,
            metadata={
                "rel_id": rel.rel_id,
                "rel_type": rel.rel_type,
                "source_entity": rel.source_id,
                "target_entity": rel.target_id,
                "causal": True,
                "evidence_artifact_id": rel.properties.get("evidence_artifact_id"),
                "evidence_uri": rel.properties.get("evidence_uri")
                or rel.properties.get("source_uri"),
            },
        )
        new_sources[ref.source_id] = ref
        causal_count += 1
    if causal_count:
        steps.append(f"Extracted {causal_count} causal relationship sources with mechanisms.")

    # ── Iterative refinement: DEEP mode, sparse results ──────────────────────
    if (
        state.reasoning_depth == ReasoningDepth.DEEP
        and len(all_entities) < 3
        and state.retries < 1
    ):
        sparse_sqs = [
            sq for sq in sub_queries_to_run
            if not sq_source_map.get(sq)
        ]
        if sparse_sqs:
            steps.append(
                f"Iterative refinement: re-querying {len(sparse_sqs)} sparse "
                f"sub-queries at depth {min(search_depth + 1, 5)}."
            )
            deeper_depth = min(search_depth + 1, 5)
            for sq in sparse_sqs:
                try:
                    async with asyncio.timeout(settings.node_timeout_seconds):
                        result = await breaker.call(
                            client.search,
                            query_text=sq,
                            max_depth=deeper_depth,
                            limit=search_limit,
                            tenant_id=state.tenant_id,
                        )
                except (CircuitOpenError, asyncio.TimeoutError):
                    continue
                if result is None:
                    continue
                sq_new_source_ids: list[str] = []
                for entity in result.entities:
                    if entity.entity_id not in seen_ids:
                        all_entities.append(entity)
                        seen_ids.add(entity.entity_id)
                all_relationships.extend(result.relationships)
                for entity in result.entities:
                    snippet = (
                        f"{', '.join(entity.labels)}: "
                        + ", ".join(f"{k}={v}" for k, v in list(entity.properties.items())[:6])
                    )
                    ref = SourceReference(
                        source_type=SourceType.NEO4J_GRAPH,
                        uri=f"neo4j://node/{entity.entity_id}",
                        title=str(entity.properties.get("name", entity.entity_id)),
                        content_snippet=snippet,
                        confidence=min(max(float(entity.score), 0.0), 1.0),
                        metadata={"entity_id": entity.entity_id, "labels": entity.labels},
                    )
                    new_sources[ref.source_id] = ref
                    sq_new_source_ids.append(ref.source_id)
                existing = sq_source_map.get(sq, [])
                sq_source_map[sq] = existing + sq_new_source_ids
            steps.append(
                f"After refinement: {len(all_entities)} entities, "
                f"{len(all_relationships)} relationships."
            )

    # ── Path-finding ────────────────────────────────────────────────────────
    # Two activation modes:
    #   1. Explicit: decomposer detected entity_pairs (e.g. "How is X related to Y?")
    #   2. Proactive: top-ranked entities automatically paired to surface causal
    #      chains. Enabled for STANDARD/DEEP with graph_proactive_paths=True.
    path_results: list[dict] = list(state.path_results)
    path_pairs_to_run: list[tuple[str, str]] = []

    if state.entity_pairs:
        for pair in state.entity_pairs[:3]:
            if len(pair) < 2 or not pair[0] or not pair[1]:
                continue
            path_pairs_to_run.append((pair[0], pair[1]))

    # Proactive path-finding: pair up the top-ranked entities by score.
    # Multi-hop queries get a larger budget (4 pairs from top 6) to surface
    # longer causal chains. Non-multi-hop caps at 2 pairs.
    if (
        settings.graph_proactive_paths
        and state.reasoning_depth != ReasoningDepth.SHALLOW
        and len(all_entities) >= 2
    ):
        if state.is_multi_hop:
            top_n, max_pairs = 6, 4
        else:
            top_n, max_pairs = 4, 2
        ranked = sorted(all_entities, key=lambda e: e.score, reverse=True)[:top_n]
        proactive_added = 0
        for i in range(len(ranked)):
            for j in range(i + 1, len(ranked)):
                if proactive_added >= max_pairs:
                    break
                name_a = str(ranked[i].properties.get("name", ""))
                name_b = str(ranked[j].properties.get("name", ""))
                if name_a and name_b and (name_a, name_b) not in path_pairs_to_run:
                    path_pairs_to_run.append((name_a, name_b))
                    proactive_added += 1
            if proactive_added >= max_pairs:
                break

    # Load feedback-adjusted weights once for this query (not per-pair).
    adjusted_weights = await _load_feedback_weights()

    if path_pairs_to_run:
        path_client = Neo4jClient()
        try:
            for name_a, name_b in path_pairs_to_run[:5]:
                try:
                    async with asyncio.timeout(settings.node_timeout_seconds):
                        aim_id_a = await path_client.lookup_entity_name(
                            name_a,
                            tenant_id=state.tenant_id,
                        )
                        aim_id_b = await path_client.lookup_entity_name(
                            name_b,
                            tenant_id=state.tenant_id,
                    )
                    if aim_id_a and aim_id_b and aim_id_a != aim_id_b:
                        async with asyncio.timeout(settings.node_timeout_seconds):
                            paths = await breaker.call(
                                path_client.find_paths,
                                source_aim_id=aim_id_a,
                                target_aim_id=aim_id_b,
                                all_shortest=state.is_multi_hop,
                                tenant_id=state.tenant_id,
                            )
                        # Phase 10: build per-edge scores via graph_scoring
                        # before aggregating. At default weights (α=0, β=1,
                        # γ=0) this collapses to the pre-Phase-10 mean of
                        # feedback-adjusted rel_type weights.
                        from aim.agents.graph_scoring import (
                            PathScoringWeights,
                            score_edge,
                            score_path,
                        )

                        try:
                            weights = PathScoringWeights(
                                alpha=float(settings.graph_edge_query_weight),
                                beta=float(settings.graph_edge_feedback_weight),
                                gamma=float(settings.graph_edge_degree_weight),
                            )
                        except (ValueError, TypeError) as exc:
                            # Defensive fallback — mis-configured or mocked
                            # settings must not break the pipeline; revert
                            # to pre-Phase-10 feedback-only weights.
                            log.warning(
                                "graph_searcher.invalid_scoring_weights",
                                error=str(exc),
                            )
                            weights = PathScoringWeights()

                        aggregation = getattr(
                            settings, "graph_path_aggregation", "mean"
                        )
                        if aggregation not in ("mean", "product"):
                            aggregation = "mean"

                        for p in paths:
                            p["queried_source_name"] = name_a
                            p["queried_target_name"] = name_b
                            edge_scores: list[float] = []
                            for r in p.get("path_rels", []):
                                rel_type = r.get("rel_type", "")
                                fb = adjusted_weights.get(rel_type, 0.4)
                                # Hooks for α / γ: callers can populate
                                # r["query_affinity"] / r["inverse_degree"]
                                # when they have real numbers. At defaults
                                # (α=0, γ=0) these values are ignored.
                                aff = float(r.get("query_affinity", 0.0))
                                inv_d = float(r.get("inverse_degree", 0.0))
                                edge_scores.append(
                                    score_edge(
                                        feedback_weight=fb,
                                        query_affinity=aff,
                                        inverse_degree=inv_d,
                                        weights=weights,
                                    )
                                )
                            p["edge_scores"] = edge_scores
                            p["path_score"] = score_path(
                                edge_scores,
                                aggregation=aggregation,
                            )
                            path_results.append(p)
                            rel_chain = " → ".join(
                                f"[{r.get('rel_type', '?')}]"
                                for r in p.get("path_rels", [])
                            )
                            steps.append(
                                f"Path found: {name_a} → {rel_chain} → {name_b} "
                                f"({p.get('hops', '?')} hops, score={p['path_score']:.2f})"
                            )
                except (CircuitOpenError, asyncio.TimeoutError):
                    steps.append(f"Path-finding timed out for: {name_a} ↔ {name_b}")
        except Exception as exc:
            log.warning("graph_searcher.pathfinding_error", error=str(exc))
        finally:
            await path_client.close()

    # Sort path_results by blended structural + query-aware relevance so the
    # synthesizer prioritizes causal chains that answer this specific question.
    if path_results:
        from aim.agents.graph_scoring import rerank_paths_for_query

        path_results = rerank_paths_for_query(state.original_query, path_results)

    # ── Path-participation score boost ─────────────────────────────────────
    # Graph paths are stronger evidence than isolated neighbourhood hits. Keep
    # the ranking mostly score-driven, but lift entities that appear in found
    # paths so multi-hop synthesis sees the full causal chain.
    if path_results and all_entities:
        path_entity_boosts: dict[str, float] = {}
        max_paths = 5 if state.is_multi_hop else 3
        for rank, p in enumerate(path_results[:max_paths]):
            rerank_score = float(
                p.get("path_rerank_score")
                or p.get("path_query_affinity")
                or p.get("path_score")
                or 0.0
            )
            boost = max(0.4, min(1.6, 0.55 + rerank_score)) / (1 + rank * 0.35)
            for node in p.get("path_nodes", []):
                aim_id = node.get("entity_id") or node.get("aim_id")
                if aim_id:
                    key = str(aim_id)
                    path_entity_boosts[key] = max(path_entity_boosts.get(key, 0.0), boost)
        if path_entity_boosts:
            boosted_count = 0
            rebuilt_entities: list[GraphEntity] = []
            for entity in all_entities:
                boost = path_entity_boosts.get(entity.entity_id)
                if boost:
                    rebuilt_entities.append(
                        entity.model_copy(update={"score": entity.score + boost})
                    )
                    boosted_count += 1
                else:
                    rebuilt_entities.append(entity)
            if boosted_count:
                all_entities = sorted(
                    rebuilt_entities,
                    key=lambda x: x.score,
                    reverse=True,
                )
                steps.append(
                    f"Query-aware path rerank boosted {boosted_count} path-participating entities."
                )

    # ── DEEP mode noise cap ────────────────────────────────────────────────
    # DEEP mode runs hybrid search with limit=40 per sub-query; after dedup
    # this leaves 60-100 candidates and pollutes the synthesizer with
    # tangentially-related entities that all share CAUSED_BY/LED_TO edges.
    # The Qwen-7B synthesizer pattern-matches them into spurious cross-
    # incident relationships ("Kafka CAUSED_BY Payment Service" hallucination
    # observed on multi-incident queries). Cap to top-25 after score-boost
    # sort so the synthesizer sees the actually-relevant cluster.
    # STANDARD mode is unaffected (already runs at limit=20).
    if state.reasoning_depth == ReasoningDepth.DEEP and len(all_entities) > 25:
        cap = 25
        all_entities = all_entities[:cap]
        steps.append(f"DEEP mode: capped graph_entities to top-{cap} after rerank.")

    # ── Missing-hop detection ───────────────────────────────────────────────
    # For multi-hop queries, flag entity_pairs with no path so downstream
    # nodes (evaluator / reloop) can issue targeted refinement sub-queries.
    missing_hops: list[str] = []
    if state.is_multi_hop and state.entity_pairs:
        found_pairs: set[tuple[str, str]] = set()
        for p in path_results:
            src_name = str(p.get("queried_source_name") or "").lower()
            tgt_name = str(p.get("queried_target_name") or "").lower()
            if not src_name or not tgt_name:
                nodes = p.get("path_nodes", [])
                if len(nodes) >= 2:
                    src_name = str(nodes[0].get("name") or "").lower()
                    tgt_name = str(nodes[-1].get("name") or "").lower()
            if src_name and tgt_name:
                found_pairs.add((src_name, tgt_name))
                found_pairs.add((tgt_name, src_name))
        for pair in state.entity_pairs:
            if len(pair) < 2 or not pair[0] or not pair[1]:
                continue
            a, b = pair[0].lower(), pair[1].lower()
            if (a, b) not in found_pairs:
                missing_hops.append(f"{pair[0]} ↔ {pair[1]}")
        if missing_hops:
            steps.append(
                f"Multi-hop gap detected: no path found between "
                f"{len(missing_hops)} entity pair(s) — flagged for refinement."
            )

    if state.access_principals:
        all_entities, all_relationships = filter_graph_by_access(
            all_entities,
            all_relationships,
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
            "graph_entities": all_entities,
            "graph_relationships": all_relationships,
            "sources": new_sources,
            "sub_query_source_map": sq_source_map,
            "reasoning_steps": steps,
            "path_results": path_results,
            "missing_hops": missing_hops,
            "retries": state.retries + 1,
        }
    )
