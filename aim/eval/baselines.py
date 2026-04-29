"""Three system runners for A.2 comparison.

Each runner takes a question string and returns a ``SystemResponse``
(defined below). The harness calls every runner on every fixture item
and feeds the responses into the pure metrics.

Runners in scope:

* ``vector_only`` — Pinecone ANN top-k, no graph, no decomposition.
  The "vanilla RAG" baseline we're trying to beat.
* ``graph_only`` — Neo4j graph traversal from question entities, no
  vector fallback. Shows what pure graph buys us — expected to win
  multi-hop but lose single-hop recall.
* ``aim_full`` — full LangGraph pipeline (decomposer → graph_searcher
  → vector_retriever → mcp_fetcher → synthesizer). The system under
  test.

Design choices:

* Runners are *thin adapters* around production code. We call the
  real graph/vector/LLM layers — a "benchmark" that bypasses the
  pipeline is meaningless.
* Each runner has its own LangGraph *or* an ad-hoc function composing
  the same primitives. Baselines don't get to cheat with their own
  retrieval tricks; they use AIM's primitives minus layers.
* IO-bound, so async. Timeout-protected so a stuck vendor can't
  deadlock the whole eval.
* Errors are captured on the response (``error`` field) and the
  metrics treat them as zeros. We want a failing baseline to *show*
  as failing, not crash the harness.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SystemResponse:
    """One system's response to one question, normalized for metrics.

    Every runner projects its native output into this shape so metrics
    don't need to know whether they're scoring a vector-only baseline
    or the full AIM pipeline.
    """

    answer: str
    # Ordered list of retrieved ids (entities for graph, chunk_ids for
    # vector). The harness reconciles id namespace via gold_entities /
    # gold_sources — see harness._project_ids.
    retrieved_ids: tuple[str, ...] = ()
    # Sources the LLM cited in its answer (chunk/source ids).
    cited_ids: tuple[str, ...] = ()
    # Graph traversal path (entity ids, in order visited). Empty for
    # vector-only baseline.
    graph_path: tuple[str, ...] = ()
    # Wall-clock seconds end-to-end. Populated by the runner, not the
    # harness, so it reflects time spent in the system under test.
    latency_s: float = 0.0
    # If the runner failed, the error message. Metrics treat this as
    # a zero response; harness surfaces the count in the report.
    error: str | None = None
    # Opaque provider metadata (model, tokens, etc.) for debugging —
    # not used by metrics.
    meta: dict[str, Any] = field(default_factory=dict)


# Runner signature: question → SystemResponse.
Runner = Callable[[str], Awaitable[SystemResponse]]


# ── Timing wrapper ─────────────────────────────────────────────────────


async def _timed(fn: Callable[[], Awaitable[SystemResponse]]) -> SystemResponse:
    """Wrap a runner body so latency is always populated on success AND
    error paths. Without this we'd have to repeat try/except + timing
    bookkeeping in every runner.
    """
    t0 = time.perf_counter()
    try:
        resp = await fn()
    except Exception as exc:  # noqa: BLE001
        log.warning("runner raised: %s", exc)
        return SystemResponse(
            answer="",
            error=f"{type(exc).__name__}: {exc}",
            latency_s=time.perf_counter() - t0,
        )
    # Preserve the runner's answer but force-populate latency if it
    # didn't already (defensive — a runner that forgets to time itself
    # shouldn't report 0.0).
    if resp.latency_s == 0.0:
        object.__setattr__(resp, "latency_s", time.perf_counter() - t0)  # frozen
    return resp


# ── Vector-only runner ─────────────────────────────────────────────────


def make_vector_only_runner(
    *,
    vector_store: Any,
    llm: Any,
    embedder: Any,
    top_k: int = 10,
) -> Runner:
    """Classic RAG: embed → ANN → stuff top-k into prompt → synthesize.

    Deliberately dumb. No decomposition, no graph, no reranker. This is
    the straw-man we're trying to beat on multi-hop.
    """

    async def run(question: str) -> SystemResponse:
        async def _body() -> SystemResponse:
            t0 = time.perf_counter()
            embedding = await embedder.embed(question)
            chunks = await vector_store.search(embedding, top_k=top_k)
            context = "\n\n".join(
                f"[{c.get('source_id', '?')}] {c.get('text', '')}"
                for c in chunks
            )
            prompt = (
                "Answer the question using only the provided sources. "
                "Cite source ids in [brackets]. If no source answers, "
                "say \"I don't know\".\n\n"
                f"Sources:\n{context}\n\nQuestion: {question}\nAnswer:"
            )
            resp = await llm.invoke(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=512,
            )
            answer = getattr(resp, "content", "") or ""
            retrieved = tuple(c.get("source_id", "") for c in chunks)
            cited = _extract_citations(answer)
            return SystemResponse(
                answer=answer,
                retrieved_ids=retrieved,
                cited_ids=cited,
                graph_path=(),  # vector-only has no graph path
                latency_s=time.perf_counter() - t0,
                meta={"top_k": top_k},
            )

        return await _timed(_body)

    return run


# ── Graph-only runner ──────────────────────────────────────────────────


def make_graph_only_runner(
    *,
    graph_client: Any,
    entity_extractor: Any,
    llm: Any,
    hops: int = 2,
    limit: int = 20,
) -> Runner:
    """Extract entities from the question → BFS neighbourhood → synthesize.

    Expected to win on multi-hop (it's literally what the graph is for)
    and lose on single-hop (no vector semantic fallback when the
    question phrasing doesn't match any entity label).
    """

    async def run(question: str) -> SystemResponse:
        async def _body() -> SystemResponse:
            t0 = time.perf_counter()
            seeds = await entity_extractor.extract(question)
            subgraph = await graph_client.neighbourhood(
                seed_ids=seeds, hops=hops, limit=limit
            )
            nodes = subgraph.get("nodes", [])
            edges = subgraph.get("edges", [])
            context = _format_subgraph(nodes, edges)
            prompt = (
                "Answer using only the provided graph. Cite entity ids in "
                "[brackets]. If the graph doesn't contain the answer, "
                "say \"I don't know\".\n\n"
                f"Graph:\n{context}\n\nQuestion: {question}\nAnswer:"
            )
            resp = await llm.invoke(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=512,
            )
            answer = getattr(resp, "content", "") or ""
            retrieved = tuple(n.get("id", "") for n in nodes)
            cited = _extract_citations(answer)
            # Path = BFS order from seeds; graph_client is expected to
            # return nodes in traversal order.
            path = tuple(n.get("id", "") for n in nodes)
            return SystemResponse(
                answer=answer,
                retrieved_ids=retrieved,
                cited_ids=cited,
                graph_path=path,
                latency_s=time.perf_counter() - t0,
                meta={"hops": hops, "seed_count": len(seeds)},
            )

        return await _timed(_body)

    return run


# ── AIM full runner ────────────────────────────────────────────────────


def make_aim_full_runner(*, agent: Any) -> Runner:
    """Run the full LangGraph agent. ``agent`` is the compiled graph.

    We call it the same way the FastAPI handler does so benchmark
    numbers track production numbers. The handler's contract: given a
    query string, return a response with answer + sources + graph_nodes.
    """

    async def run(question: str) -> SystemResponse:
        async def _body() -> SystemResponse:
            import uuid as _uuid
            t0 = time.perf_counter()
            result = await agent.ainvoke(
                {
                    "query_id": _uuid.uuid4(),
                    "original_query": question,
                    "query": question,
                    "reasoning_depth": "standard",
                }
            )
            # LangGraph terminal state shape — align with how
            # synthesizer populates it.
            answer = result.get("answer") or result.get("final_answer") or ""
            sources = result.get("sources") or result.get("citations") or []
            graph_nodes = result.get("graph_nodes") or []
            graph_path = result.get("graph_path") or graph_nodes

            retrieved = tuple(
                (s.get("source_id") or s.get("id") or "") for s in sources
            ) + tuple(
                (n.get("id") or n.get("aim_id") or "") for n in graph_nodes
            )
            cited = tuple(
                (s.get("source_id") or s.get("id") or "")
                for s in sources
                if s.get("cited")
            ) or _extract_citations(answer)
            path = tuple(
                (p.get("id") or p.get("aim_id") or "") if isinstance(p, dict) else str(p)
                for p in graph_path
            )
            return SystemResponse(
                answer=answer,
                retrieved_ids=retrieved,
                cited_ids=cited,
                graph_path=path,
                latency_s=time.perf_counter() - t0,
                meta={"raw_keys": list(result.keys())},
            )

        return await _timed(_body)

    return run


# ── Helpers ────────────────────────────────────────────────────────────


_CITE_RE = None


def _extract_citations(answer: str) -> tuple[str, ...]:
    """Pull ``[source_id]`` style citations out of an answer.

    Lives here so both baselines use the same parsing rule. AIM's
    synthesizer usually provides structured citations; this is the
    fallback for baselines that don't.
    """
    import re

    global _CITE_RE
    if _CITE_RE is None:
        # Matches [alphanum/_/-/:] inside brackets. Rejects whitespace-
        # only brackets (which Markdown sometimes produces).
        _CITE_RE = re.compile(r"\[([A-Za-z0-9_:\-/.]+)\]")
    seen: list[str] = []
    for m in _CITE_RE.finditer(answer or ""):
        cid = m.group(1)
        if cid and cid not in seen:
            seen.append(cid)
    return tuple(seen)


def _format_subgraph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    """Render a subgraph as plaintext for LLM context.

    One line per node (id + label + name), one per edge (src -rel-> dst).
    Terse so graph-only doesn't get to cheat with richer context than
    vector-only gets.
    """
    lines: list[str] = []
    for n in nodes[:50]:  # cap for prompt budget
        nid = n.get("id") or n.get("aim_id") or "?"
        name = n.get("name") or n.get("title") or ""
        labels = ",".join(n.get("labels", [])) or "Entity"
        lines.append(f"NODE [{nid}] {labels}: {name}")
    for e in edges[:80]:
        src = e.get("source") or e.get("src") or "?"
        dst = e.get("target") or e.get("dst") or "?"
        rel = e.get("type") or e.get("rel") or "REL"
        lines.append(f"EDGE [{src}] -{rel}-> [{dst}]")
    return "\n".join(lines)
