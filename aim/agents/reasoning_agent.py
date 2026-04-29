"""AIM Reasoning Agent — LangGraph StateGraph with node-level timeouts.

Flow:
  START
    └─► decompose
          ├─► search_graph  ─┐  (parallel fan-out; search_graph is a no-op when SHALLOW)
          └─► fetch_mcp     ─┴─► retrieve_vectors ─► synthesize ─► END

Both ``run_reasoning_agent`` (sync, returns QueryResponse) and
``stream_reasoning_agent`` (async generator, yields StreamChunk) share the
same ``_timed_node``-wrapped callables so per-node timeouts and Prometheus
metrics are applied identically on both paths.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import AsyncGenerator
from uuid import UUID

import structlog
from langgraph.graph import END, START, StateGraph

from aim.agents.nodes.decomposer import decompose_query
from aim.agents.nodes.evaluator import evaluate_answer
from aim.agents.nodes.graph_searcher import search_knowledge_graph
from aim.agents.nodes.mcp_fetcher import fetch_mcp_context
from aim.agents.nodes.synthesizer import (
    _build_context_block,
    _extract_citation_map,
    _normalize_citation_tags,
    _compute_confidence,
    build_provenance,
    build_sources_summary,
    synthesize_answer,
)
from aim.agents.nodes.vector_retriever import retrieve_vectors
from aim.agents.hybrid_retriever import fuse_by_graph_rerank
from aim.agents.branch_selector import (
    BranchCandidate,
    select_best,
    select_best_with_tiebreaker,
)
from aim.agents.state import AgentState
from aim.schemas.query import CostInfo, QueryResponse, ReasoningDepth, StreamChunk, SubQueryResult
from aim.utils.metrics import (
    CONVERSATION_TURNS,
    COST_USD_TOTAL,
    NODE_ERRORS,
    NODE_LATENCY,
    QUERY_LATENCY,
    QUERY_TOTAL,
    TOKEN_EMBEDDING_TOTAL,
    TOKEN_INPUT_TOTAL,
    TOKEN_OUTPUT_TOTAL,
)

log = structlog.get_logger(__name__)

def _compute_cost(
    input_tokens: int,
    output_tokens: int,
    embedding_tokens: int,
) -> CostInfo:
    """Compute cost using configurable pricing from settings."""
    from aim.config import get_settings
    s = get_settings()
    input_rate = s.llm_input_cost_per_mtok / 1_000_000
    output_rate = s.llm_output_cost_per_mtok / 1_000_000
    embed_rate = s.embedding_cost_per_mtok / 1_000_000
    llm_cost = input_tokens * input_rate + output_tokens * output_rate
    embed_cost = embedding_tokens * embed_rate
    return CostInfo(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        embedding_tokens=embedding_tokens,
        estimated_cost_usd=round(llm_cost + embed_cost, 6),
    )


def _emit_token_metrics(model: str, cost: CostInfo) -> None:
    from aim.config import get_settings
    s = get_settings()
    TOKEN_INPUT_TOTAL.labels(model=model).inc(cost.input_tokens)
    TOKEN_OUTPUT_TOTAL.labels(model=model).inc(cost.output_tokens)
    TOKEN_EMBEDDING_TOTAL.labels(model=s.embedding_model).inc(cost.embedding_tokens)
    input_rate = s.llm_input_cost_per_mtok / 1_000_000
    output_rate = s.llm_output_cost_per_mtok / 1_000_000
    embed_rate = s.embedding_cost_per_mtok / 1_000_000
    llm_cost = cost.input_tokens * input_rate + cost.output_tokens * output_rate
    embed_cost = cost.embedding_tokens * embed_rate
    COST_USD_TOTAL.labels(component="llm").inc(llm_cost)
    COST_USD_TOTAL.labels(component="embedding").inc(embed_cost)


# ── Timeout + metrics wrapper ─────────────────────────────────────────────────

def _timed_node(name: str, fn):
    """Wrap a node coroutine with per-node timeout + Prometheus metrics."""
    async def _wrapper(state: AgentState) -> AgentState:
        from aim.config import get_settings
        settings = get_settings()
        t0 = time.perf_counter()
        try:
            async with asyncio.timeout(settings.node_timeout_seconds):
                return await fn(state)
        except asyncio.TimeoutError:
            elapsed = time.perf_counter() - t0
            log.error(f"{name}.timeout", timeout=settings.node_timeout_seconds, elapsed=elapsed)
            NODE_ERRORS.labels(node_name=name, error_type="timeout").inc()
            updates = {
                "reasoning_steps": [
                    *state.reasoning_steps,
                    f"{name} timed out after {settings.node_timeout_seconds}s.",
                ]
            }
            if name == "decompose":
                updates.update({
                    "sub_queries": [state.original_query],
                    "query_intent": "general",
                    "entity_pairs": [],
                    "is_multi_hop": False,
                })
            return state.model_copy(
                update=updates
            )
        finally:
            NODE_LATENCY.labels(node_name=name).observe(time.perf_counter() - t0)

    _wrapper.__name__ = name
    return _wrapper


# ── Module-level wrapped nodes ────────────────────────────────────────────────

async def _retrieve_vectors_with_fusion(state: AgentState) -> AgentState:
    """Vector retrieval, optionally followed by graph-rerank fusion.

    Phase γ.1: when ``settings.retrieval_fusion_mode == "graph_reranks_vector"``,
    the vector snippet list is reordered so snippets whose metadata points at
    a graph-retrieved entity rise to the top. The fusion is a pure
    post-processing pass — if no graph entities are present, or the mode is
    left at the default ``"parallel"``, behaviour is byte-identical to
    legacy.
    """
    state = await retrieve_vectors(state)
    from aim.config import get_settings
    s = get_settings()
    # Per-branch override takes precedence over process-wide config. Enables
    # the branch orchestrator (γ.2) to fan out with different fusion recipes
    # without racing on module-level settings.
    mode = state.fusion_mode_override or s.retrieval_fusion_mode
    if mode != "graph_reranks_vector":
        return state
    if not state.vector_snippets or not state.graph_entities:
        return state
    graph_ids = [e.entity_id for e in state.graph_entities]
    fused = fuse_by_graph_rerank(
        graph_ids,
        state.vector_snippets,
        boost=s.retrieval_fusion_boost,
    )
    return state.model_copy(update={"vector_snippets": fused})


_decompose_fn        = _timed_node("decompose",        decompose_query)
_search_graph_fn     = _timed_node("search_graph",     search_knowledge_graph)
_fetch_mcp_fn        = _timed_node("fetch_mcp",        fetch_mcp_context)
_retrieve_vectors_fn = _timed_node("retrieve_vectors", _retrieve_vectors_with_fusion)
_synthesize_fn       = _timed_node("synthesize",       synthesize_answer)
_evaluate_fn         = _timed_node("evaluate",         evaluate_answer)


# ── Graph ─────────────────────────────────────────────────────────────────────

def _evaluate_route(state: AgentState) -> str:
    """Conditional edge from evaluate: reloop on low score, else finish."""
    return "reloop" if state.needs_reloop else "done"


def build_graph() -> StateGraph:
    """Build the LangGraph StateGraph with an adaptive evaluation loop.

    Flow::

      START
        └─► decompose
              ├─► search_graph  ─┐  (parallel fan-out)
              └─► fetch_mcp     ─┴─► retrieve_vectors ─► synthesize ─► evaluate
                                                                          │
                                          ┌── (reloop, ≤ max_loops) ─────┘
                                          └─► decompose …                 │
                                                                     (done) ─► END

    SHALLOW depth is handled *inside* ``search_knowledge_graph``.
    The evaluation loop is bounded by ``settings.max_reasoning_loops``; the
    LangGraph ``recursion_limit`` is scaled accordingly by
    :func:`_compute_recursion_limit` so deep pipelines aren't truncated.
    """
    g = StateGraph(AgentState)

    g.add_node("decompose",        _decompose_fn)
    g.add_node("search_graph",     _search_graph_fn)
    g.add_node("fetch_mcp",        _fetch_mcp_fn)
    g.add_node("retrieve_vectors", _retrieve_vectors_fn)
    g.add_node("synthesize",       _synthesize_fn)
    g.add_node("evaluate",         _evaluate_fn)

    g.add_edge(START, "decompose")

    # Three-way fan-out: graph search, MCP fetch, and vector retrieval all
    # depend ONLY on decompose's sub_queries. Run them concurrently.
    # SHALLOW short-circuits inside search_graph.
    g.add_edge("decompose", "search_graph")
    g.add_edge("decompose", "fetch_mcp")
    g.add_edge("decompose", "retrieve_vectors")

    # Stable 3-way join into synthesize.
    g.add_edge("search_graph",     "synthesize")
    g.add_edge("fetch_mcp",        "synthesize")
    g.add_edge("retrieve_vectors", "synthesize")
    g.add_edge("synthesize",       "evaluate")

    # Conditional: reloop back to decompose or finish
    g.add_conditional_edges("evaluate", _evaluate_route, {
        "reloop": "decompose",
        "done":   END,
    })

    return g


_compiled_graph = build_graph().compile()


# ── Branch fan-out ────────────────────────────────────────────────────────────
#
# When ``settings.reasoning_branch_count > 1``, run the compiled graph N times
# in parallel with different ``fusion_mode_override`` values and pick the
# highest-scoring candidate answer via ``branch_selector.select_best``.
#
# Default (count == 1) is a no-op: the existing single-branch path runs
# unchanged. Cost scales linearly with branch count (N× retrieval + N×
# synthesizer), so production rollout should start at N=1 and flip to N=2
# after cache warmth is verified.

# Orthogonal branch strategies — differ on retrieval **modality**, not on
# post-processing knob. γ.3 rewired this after a panel audit flagged the
# prior palette (three fusion variants) as fan-out over one dimension.
#
# Each strategy is ``(branch_id, overrides_dict)`` where ``overrides_dict``
# mutates the initial AgentState before invoking the compiled graph:
#
# * ``hybrid``      — both modalities on, graph reranks vector. The
#                     full-machinery baseline.
# * ``graph_only``  — vector search off; answers derived purely from graph
#                     traversal. Wins when the corpus is entity-heavy and
#                     the vector index has thin coverage.
# * ``vector_only`` — graph search off; answers derived purely from semantic
#                     similarity. Wins when the query is paraphrase-shaped
#                     and no named entity is present.
#
# Orchestrator takes a ``reasoning_branch_count`` slice of this list, so
# N=1 is hybrid (current behaviour), N=2 adds graph_only, N=3 adds
# vector_only. Fan-out failures are tolerated in _run_branches_and_select.
_BRANCH_STRATEGIES: list[tuple[str, dict[str, object]]] = [
    ("hybrid",      {"fusion_mode_override": "graph_reranks_vector"}),
    ("graph_only",  {"vector_search_enabled": False, "fusion_mode_override": "parallel"}),
    ("vector_only", {"graph_search_enabled": False, "fusion_mode_override": "parallel"}),
]


def _candidate_from_state(branch_id: str, state: AgentState) -> BranchCandidate:
    """Project the end-of-pipeline :class:`AgentState` into a scoring-ready
    :class:`BranchCandidate`.

    Kept in one place so the branch orchestrator and the pipeline-internal
    scoring (if we ever want it) agree on how an answer is measured.
    """
    cited_ids: set[str] = set()
    for ids in state.citation_map.values():
        cited_ids.update(ids)
    covered = sum(
        1 for sq in state.sub_queries
        if state.sub_query_source_map.get(sq)
    )
    confidence = (
        state.provenance.overall_confidence
        if state.provenance is not None
        else 0.0
    )
    return BranchCandidate(
        branch_id=branch_id,
        answer_text=state.answer,
        cited_source_ids=tuple(cited_ids),
        total_sources=len(state.sources),
        covered_sub_queries=covered,
        total_sub_queries=len(state.sub_queries),
        confidence=confidence,
    )


async def _run_single_branch(
    initial_state: AgentState,
    recursion_limit: int,
    overrides: dict[str, object],
) -> AgentState:
    """Invoke the compiled graph once with the branch's strategy overrides
    applied to the initial AgentState. ``overrides`` is an opaque dict of
    AgentState field values (fusion mode, modality toggles, etc.) so new
    branch axes can be added without touching this wire-in."""
    branch_state = initial_state.model_copy(update=overrides)
    final = await _compiled_graph.ainvoke(
        branch_state,
        config={"recursion_limit": recursion_limit},
    )
    # LangGraph returns a dict-shaped state; rehydrate to AgentState for
    # downstream projection. (``ainvoke`` may return either depending on
    # version; be defensive.)
    if isinstance(final, AgentState):
        return final
    return AgentState.model_validate(final)


async def _run_branches_and_select(
    initial_state: AgentState,
    recursion_limit: int,
    branch_count: int,
) -> AgentState:
    """Run ``branch_count`` branches in parallel and return the winner's
    final state.

    If any branch raises, the remaining branches are allowed to complete;
    a branch that fails is simply excluded from selection. If *all*
    branches fail, the first exception is re-raised so the caller sees a
    real error rather than a silently-empty answer.
    """
    strategies = _BRANCH_STRATEGIES[:branch_count]
    results = await asyncio.gather(
        *(
            _run_single_branch(initial_state, recursion_limit, overrides)
            for _, overrides in strategies
        ),
        return_exceptions=True,
    )

    candidates: list[tuple[BranchCandidate, AgentState]] = []
    first_exc: BaseException | None = None
    for (name, _), r in zip(strategies, results):
        if isinstance(r, BaseException):
            first_exc = first_exc or r
            log.warning("reasoning_agent.branch_failed", branch=name, error=str(r))
            continue
        candidates.append((_candidate_from_state(name, r), r))

    if not candidates:
        assert first_exc is not None
        raise first_exc

    # δ.3 Move 3: when evaluator_mode == "llm_tiebreaker", ask an LLM
    # judge to break near-ties in heuristic score. Otherwise use the
    # pure-function heuristic winner (current behaviour, zero cost).
    from aim.config import get_settings
    settings = get_settings()
    cand_list = [c for c, _ in candidates]
    if settings.evaluator_mode == "llm_tiebreaker" and len(cand_list) >= 2:
        winner_cand, scoreboard, judge_invoked = await select_best_with_tiebreaker(
            cand_list,
            threshold=settings.evaluator_llm_tiebreaker_threshold,
            judge=_make_llm_branch_judge(),
        )
        log.info(
            "reasoning_agent.branch_selected",
            winner=winner_cand.branch_id,
            scoreboard=scoreboard,
            mode="llm_tiebreaker",
            judge_invoked=judge_invoked,
        )
    else:
        winner_cand, scoreboard = select_best(cand_list)
        log.info(
            "reasoning_agent.branch_selected",
            winner=winner_cand.branch_id,
            scoreboard=scoreboard,
        )
    winner_state = next(s for c, s in candidates if c.branch_id == winner_cand.branch_id)
    return winner_state


def _make_llm_branch_judge():
    """Build an async judge callable that asks the LLM to pick between
    near-tied branch candidates.

    Isolated as a factory so tests can swap it out and so the LLM
    provider is only imported when the llm_tiebreaker mode is actually
    engaged (keeps pure-heuristic installs import-clean).
    """
    async def _judge(contenders: list[BranchCandidate]) -> str:
        from aim.llm import get_llm_provider

        bullets = "\n".join(
            f"- branch_id={c.branch_id}: "
            f"cited={len(set(c.cited_source_ids))}/{c.total_sources}, "
            f"sub_q_coverage={c.covered_sub_queries}/{c.total_sub_queries}, "
            f"confidence={c.confidence:.2f}, "
            f"answer_preview={c.answer_text[:200]!r}"
            for c in contenders
        )
        prompt = (
            "You are picking between near-tied candidate answers from a "
            "tree-of-thought retrieval pipeline. Each candidate was scored "
            "equally by a heuristic; your job is to pick the one that is "
            "most faithful to its sources and most completely addresses "
            "the question.\n\n"
            f"Candidates:\n{bullets}\n\n"
            "Respond with ONLY the chosen branch_id (no prose, no "
            "punctuation, no explanation)."
        )
        llm = get_llm_provider()
        resp = await llm.invoke(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=32,
        )
        return resp.content.strip()

    return _judge


# Nodes per reasoning pass: decompose → search_graph + fetch_mcp →
# retrieve_vectors → synthesize → evaluate = 6 transitions per loop.
# Add headroom for LangGraph's internal START/END/join bookkeeping.
_NODES_PER_LOOP = 6
_LOOP_OVERHEAD = 4


def _compute_recursion_limit(max_loops: int) -> int:
    """Scale LangGraph's ``recursion_limit`` to the configured reloop budget.

    LangGraph's default is 25 — enough for a single pass but not for
    ``max_reasoning_loops=5``.  Each reloop replays all 6 nodes, so we need
    ``(max_loops + 1) * 6 + overhead`` steps of headroom.  Bounded to 100 to
    keep runaway graphs from burning unbounded work.
    """
    try:
        loops = int(max_loops)
    except (TypeError, ValueError):
        loops = 3
    needed = (loops + 1) * _NODES_PER_LOOP + _LOOP_OVERHEAD
    return max(25, min(needed, 100))


# ── Sync path ─────────────────────────────────────────────────────────────────

async def run_reasoning_agent(
    query: str,
    query_id: UUID,
    reasoning_depth: ReasoningDepth = ReasoningDepth.STANDARD,
    vector_filters: dict | None = None,
    thread_id: UUID | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    tenant_id: str = "",
    access_principals: list[str] | None = None,
) -> QueryResponse:
    from aim.config import get_settings

    settings = get_settings()
    t0 = time.perf_counter()
    depth_label = reasoning_depth.value
    history = conversation_history or []

    log.info(
        "reasoning_agent.start",
        query_id=str(query_id),
        thread_id=str(thread_id) if thread_id else None,
        depth=depth_label,
        history_turns=len(history) // 2,
        query_hash=hashlib.sha256(query.encode()).hexdigest()[:16],
    )

    if history:
        CONVERSATION_TURNS.observe(len(history) // 2)

    initial_state = AgentState(
        query_id=query_id,
        original_query=query,
        reasoning_depth=reasoning_depth,
        vector_filters=vector_filters,
        thread_id=thread_id,
        conversation_history=history,
        tenant_id=tenant_id,
        access_principals=access_principals or ["public"],
        # Must be set explicitly: LangGraph's channel adapter treats Pydantic
        # defaults as type-zero (False for bool), so omitting these makes the
        # graph search and vector search nodes skip themselves. eval_live.py
        # always sets them; the API path didn't, which broke live ingest demos.
        graph_search_enabled=True,
        vector_search_enabled=True,
    )
    recursion_limit = _compute_recursion_limit(settings.max_reasoning_loops)
    branch_count = max(1, min(int(settings.reasoning_branch_count), 3))

    try:
        if branch_count == 1:
            raw_final = await _compiled_graph.ainvoke(
                initial_state,
                config={"recursion_limit": recursion_limit},
            )
            final_state = (
                raw_final
                if isinstance(raw_final, AgentState)
                else AgentState.model_validate(raw_final)
            )
        else:
            final_state = await _run_branches_and_select(
                initial_state, recursion_limit, branch_count
            )
        QUERY_TOTAL.labels(status="success", depth=depth_label).inc()
    except Exception:
        QUERY_TOTAL.labels(status="error", depth=depth_label).inc()
        raise

    latency_s = time.perf_counter() - t0
    QUERY_LATENCY.labels(depth=depth_label).observe(latency_s)

    log.info(
        "reasoning_agent.done",
        query_id=str(query_id),
        latency_ms=round(latency_s * 1000, 1),
        sources=len(final_state.sources),
        answer_chars=len(final_state.answer),
        input_tokens=final_state.input_tokens,
        output_tokens=final_state.output_tokens,
    )

    if final_state.provenance is None:
        raise RuntimeError("Synthesizer did not produce a ProvenanceMap")

    cost = _compute_cost(
        final_state.input_tokens,
        final_state.output_tokens,
        final_state.embedding_tokens,
    )
    _emit_token_metrics(settings.llm_model, cost)

    sub_query_results = [
        SubQueryResult(
            sub_query_id=f"sq_{i}",
            sub_query_text=sq,
            graph_hits=sum(
                1 for sid in final_state.sub_query_source_map.get(sq, [])
                if sid in final_state.sources
                and final_state.sources[sid].source_type.value == "neo4j_graph"
            ),
            vector_hits=sum(
                1 for sid in final_state.sub_query_source_map.get(sq, [])
                if sid in final_state.sources
                and final_state.sources[sid].source_type.value == "pinecone_vector"
            ),
            mcp_hits=sum(
                1 for sid in final_state.sub_query_source_map.get(sq, [])
                if sid in final_state.sources
                and final_state.sources[sid].source_type.value in ("slack_mcp", "jira_mcp")
            ),
        )
        for i, sq in enumerate(final_state.sub_queries)
    ]

    return QueryResponse(
        query_id=query_id,
        thread_id=thread_id,
        original_query=query,
        answer=final_state.answer,
        sub_query_results=sub_query_results,
        provenance=final_state.provenance,
        model_used=settings.llm_model,
        latency_ms=round(latency_s * 1000, 1),
        cost_info=cost,
    )


# ── Streaming path ────────────────────────────────────────────────────────────

async def stream_reasoning_agent(
    query: str,
    query_id: UUID,
    reasoning_depth: ReasoningDepth = ReasoningDepth.STANDARD,
    vector_filters: dict | None = None,
    thread_id: UUID | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    tenant_id: str = "",
    access_principals: list[str] | None = None,
) -> AsyncGenerator[StreamChunk, None]:
    """Async generator yielding StreamChunk events for SSE.

    The final ``done`` event includes:
    - ``sources``: lightweight list of sources used (for frontend display)
    - ``confidence``: computed from actual retrieval scores
    - ``thread_id``: echoed back so the client can associate the response
    - ``cost_info``: token usage and estimated cost

    Token streaming is done via ``llm.astream``; the full answer is buffered
    server-side so provenance can be computed before the done event is sent.
    """
    from aim.config import get_settings
    from aim.llm import get_llm_provider
    settings = get_settings()

    history = conversation_history or []

    state = AgentState(
        query_id=query_id,
        original_query=query,
        reasoning_depth=reasoning_depth,
        vector_filters=vector_filters,
        thread_id=thread_id,
        conversation_history=history,
        tenant_id=tenant_id,
        access_principals=access_principals or ["public"],
    )
    seq = 0

    if history:
        CONVERSATION_TURNS.observe(len(history) // 2)

    # Reasoning loop — runs once normally, up to max_reasoning_loops reloops
    full_answer = ""
    confidence = 0.0
    sources_summary: list[dict] = []
    total_input = 0
    total_output = 0

    for _loop_iter in range(settings.max_reasoning_loops + 1):
        # Phase 1 — decompose
        state = await _decompose_fn(state)
        for i, sq in enumerate(state.sub_queries):
            yield StreamChunk(
                chunk_type="sub_query",
                content=f"[{i + 1}] {sq}",
                query_id=query_id,
                sequence=seq,
            )
            seq += 1

        # Phase 2 — parallel retrieval
        state_g, state_m = await asyncio.gather(
            _search_graph_fn(state),
            _fetch_mcp_fn(state),
        )

        merged_sq_map: dict[str, list[str]] = {
            sq: (
                state_g.sub_query_source_map.get(sq, [])
                + state_m.sub_query_source_map.get(sq, [])
            )
            for sq in state.sub_queries
        }

        state = state.model_copy(update={
            "graph_entities":       state_g.graph_entities,
            "graph_relationships":  state_g.graph_relationships,
            "mcp_context":          state_m.mcp_context,
            "sources":              {**state_g.sources, **state_m.sources},
            "sub_query_source_map": merged_sq_map,
            "reasoning_steps":      [*state.reasoning_steps, *state_g.reasoning_steps, *state_m.reasoning_steps],
            "input_tokens":         state_g.input_tokens + state_m.input_tokens,
            "output_tokens":        state_g.output_tokens + state_m.output_tokens,
            "missing_hops":         state_g.missing_hops,
            "path_results":         state_g.path_results,
        })

        state = await _retrieve_vectors_fn(state)

        yield StreamChunk(
            chunk_type="sub_query",
            content=f"Retrieved {len(state.sources)} sources. Synthesizing…",
            query_id=query_id,
            sequence=seq,
        )
        seq += 1

        # Phase 3 — stream synthesis tokens, buffer full answer for provenance
        from aim.agents.nodes.synthesizer import _build_messages
        context_block = await _build_context_block(state)
        messages = _build_messages(state, context_block)

        llm = get_llm_provider()

        answer_chunks: list[str] = []
        stream_input_tokens = 0
        stream_output_tokens = 0

        async for token_chunk in llm.stream(
            messages,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        ):
            if token_chunk.content:
                answer_chunks.append(token_chunk.content)
                yield StreamChunk(chunk_type="token", content=token_chunk.content, query_id=query_id, sequence=seq)
                seq += 1
            if token_chunk.is_final:
                stream_input_tokens = token_chunk.input_tokens
                stream_output_tokens = token_chunk.output_tokens

        # Compute provenance from the buffered answer
        full_answer = _normalize_citation_tags("".join(answer_chunks))

        # ── Streaming-path post-pass: responder injection ──────────────────
        # The sync synthesize_answer node does many post-LLM fixups (no-evidence
        # refusal, fact-absence refusal, responder injection, fallback citation).
        # The streaming path bypassed all of that, so for the most-impactful
        # one — making sure incident-question answers always include the
        # graph's RESPONDED_TO Person entities — we inline it here too.
        # Qwen-7B reliably skips RESPONDED_TO Persons even when prompted; this
        # deterministic post-pass guarantees they surface in the streaming UI.
        import re as _re_resp
        _inc_re_s = _re_resp.compile(r"\bINC-\d{4}-\d+\b")
        _inc_ids_s = set(_inc_re_s.findall(query))
        if _inc_ids_s and full_answer and not full_answer.startswith("I don't know"):
            responder_names_s: list[str] = []
            seen_resp_s: set[str] = set()
            for rel in state.graph_relationships:
                if rel.rel_type != "RESPONDED_TO":
                    continue
                for cand_id in (rel.source_id, rel.target_id):
                    ent = next(
                        (e for e in state.graph_entities if e.entity_id == cand_id),
                        None,
                    )
                    if ent is None:
                        continue
                    name = str(ent.properties.get("name", "")).strip()
                    if not name or name in seen_resp_s:
                        continue
                    if _inc_re_s.search(name):
                        continue  # skip the incident entity itself
                    other_ent = next(
                        (e for e in state.graph_entities
                         if e.entity_id == (rel.target_id if cand_id == rel.source_id else rel.source_id)),
                        None,
                    )
                    if other_ent is None:
                        continue
                    other_name = str(other_ent.properties.get("name", ""))
                    if not any(inc in other_name for inc in _inc_ids_s):
                        continue
                    seen_resp_s.add(name)
                    responder_names_s.append(name)
            if responder_names_s and not any(n in full_answer for n in responder_names_s):
                names_str_s = ", ".join(responder_names_s[:5])
                injection = f"\n\n**Responders** (per the graph): {names_str_s}."
                full_answer = full_answer.rstrip() + injection
                # Stream the injected line so the UI shows it appended in real time.
                yield StreamChunk(
                    chunk_type="token",
                    content=injection,
                    query_id=query_id,
                    sequence=seq,
                )
                seq += 1
                log.info(
                    "stream.responder_injected",
                    incident_ids=sorted(_inc_ids_s),
                    responders=responder_names_s[:5],
                )

        valid_source_ids = set(state.sources.keys())
        citation_map = _extract_citation_map(full_answer, valid_source_ids)
        confidence = _compute_confidence(state.sources, citation_map)
        sources_summary = build_sources_summary(state.sources)

        total_input = state.input_tokens + stream_input_tokens
        total_output = state.output_tokens + stream_output_tokens

        # Phase 4 — evaluate: decide whether to reloop
        state = state.model_copy(update={
            "answer": full_answer,
            "citation_map": citation_map,
            "input_tokens": total_input,
            "output_tokens": total_output,
        })
        state = await _evaluate_fn(state)

        if not state.needs_reloop:
            break

        # Relooping — tell the client
        yield StreamChunk(
            chunk_type="sub_query",
            content=f"Evaluation score {state.evaluation_score:.2f} — re-searching for better evidence…",
            query_id=query_id,
            sequence=seq,
        )
        seq += 1

    cost = _compute_cost(total_input, total_output, state.embedding_tokens)
    _emit_token_metrics(settings.llm_model, cost)

    # Sovereignty audit — record the streaming LLM dispatch for compliance.
    # Mirrors the sync synthesizer's audit call so every external LLM hit is
    # logged regardless of the code path.
    try:
        from aim.utils.audit_log import get_audit_logger
        from aim.utils.data_classification import get_data_classifier
        from aim.agents.nodes.synthesizer import _redact_free_text, _classify_source

        classifier = get_data_classifier()
        classifications: set[str] = set()
        vector_redactions = 0
        mcp_redactions = 0
        field_redactions = 0

        for e in state.graph_entities[:30]:
            for level in classifier.classify_properties(e.properties).values():
                classifications.add(level.name)
                if level.name in ("RESTRICTED", "CONFIDENTIAL"):
                    field_redactions += 1

        for src_id, ref in state.sources.items():
            classifications.add(_classify_source(ref, classifier))

        for s in state.vector_snippets:
            _, _cls, n = _redact_free_text(s.get("text", ""), classifier)
            vector_redactions += n
        if state.mcp_context:
            for _, text in state.mcp_context.as_text_chunks():
                _, _cls, n = _redact_free_text(text, classifier)
                mcp_redactions += n

        mcp_count = state.mcp_context.total_items if state.mcp_context else 0
        corrective = None
        if field_redactions or vector_redactions or mcp_redactions:
            corrective = (
                f"fields={field_redactions} "
                f"vector={vector_redactions} mcp={mcp_redactions}"
            )

        await get_audit_logger().log_llm_call(
            query_id=state.query_id,
            provider=settings.llm_provider,
            model=settings.llm_model,
            num_entities=len(state.graph_entities),
            num_snippets=len(state.vector_snippets),
            num_mcp_items=mcp_count,
            classifications_sent=sorted(classifications),
            estimated_input_tokens=stream_input_tokens,
            tenant_id=state.tenant_id or "default",
            query_excerpt=state.original_query[:200],
            vector_redactions=vector_redactions,
            mcp_redactions=mcp_redactions,
            field_redactions=field_redactions,
            corrective_action=corrective,
        )
    except Exception as exc:
        log.debug("stream.audit_error", error=str(exc))

    # Build structured provenance for the final answer
    provenance_map = build_provenance(state, citation_map, confidence)

    yield StreamChunk(
        chunk_type="done",
        content="",
        query_id=query_id,
        sequence=seq,
        thread_id=thread_id,
        sources=sources_summary,
        confidence=confidence,
        cost_info=cost,
        provenance=provenance_map.model_dump(mode="json"),
    )
