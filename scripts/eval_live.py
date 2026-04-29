"""A.2 live benchmark runner — wires production singletons to the eval harness.

Runs vector_only vs graph_only vs aim_full on the 31-item ground-truth
fixture and writes a markdown report with per-category NDCG deltas.

Usage:
    python -m scripts.eval_live
    python -m scripts.eval_live --fixture tests/eval/fixtures/ground_truth.yaml

Requires the full infra stack up:
    - Neo4j at NEO4J_URI (default bolt://localhost:7687)
    - Qdrant at VECTOR_DB_URL (default http://localhost:6333)
    - Redis at REDIS_URL (default redis://localhost:6379)
    - Ollama (or configured LLM provider) reachable at LLM_BASE_URL

And the demo seed already loaded:
    python -m scripts.seed_demo
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# ── Adapters ──────────────────────────────────────────────────────────────────


class _VectorStoreAdapter:
    """Bridges the baselines' `.search(embedding, top_k)` onto the live
    vectordb provider's `.query(embedding, top_k)`.
    """

    def __init__(self, provider: Any) -> None:
        self._p = provider

    async def search(self, embedding: list[float], top_k: int = 10) -> list[dict[str, Any]]:
        hits = await self._p.query(embedding=embedding, top_k=top_k)
        # Project to baseline's expected {source_id, text} shape.
        out: list[dict[str, Any]] = []
        for h in hits:
            meta = h.get("metadata") or {}
            out.append({
                "source_id": meta.get("source_id") or meta.get("aim_id") or h.get("id", ""),
                "text": h.get("text", "") or meta.get("text", ""),
                "score": h.get("score", 0.0),
            })
        return out


class _EmbedderAdapter:
    """The live embedding provider already exposes `.embed(text) -> list[float]`."""

    def __init__(self, provider: Any) -> None:
        self._p = provider

    async def embed(self, text: str) -> list[float]:
        return await self._p.embed(text)


class _GraphClientAdapter:
    """Bridges baseline's `.neighbourhood(seed_ids, hops, limit)` onto
    Neo4jClient. Uses a Cypher BFS over the tenant-scoped subgraph.
    """

    def __init__(self, client: Any) -> None:
        self._c = client

    async def neighbourhood(
        self, *, seed_ids: list[str], hops: int = 2, limit: int = 20,
    ) -> dict[str, list[dict[str, Any]]]:
        if not seed_ids:
            return {"nodes": [], "edges": []}

        # Raw Cypher via the driver — stay within the client's timeout.
        import asyncio as _asyncio
        driver = self._c._driver  # noqa: SLF001
        database = getattr(self._c, "_database", None) or "neo4j"
        query = f"""
        MATCH (seed:Entity) WHERE seed.aim_id IN $seed_ids
        CALL {{
            WITH seed
            MATCH path = (seed)-[*1..{int(hops)}]-(n:Entity)
            RETURN nodes(path) AS ns, relationships(path) AS rs
            LIMIT $limit
        }}
        WITH collect(ns) AS all_nodes, collect(rs) AS all_rels
        RETURN all_nodes, all_rels
        """
        nodes_by_id: dict[str, dict[str, Any]] = {}
        edges_by_id: dict[str, dict[str, Any]] = {}
        async with _asyncio.timeout(15.0):
            async with driver.session(database=database) as session:
                result = await session.run(query, seed_ids=list(seed_ids), limit=int(limit))
                async for record in result:
                    for ns in record["all_nodes"] or []:
                        for n in ns:
                            aim_id = n.get("aim_id") or str(n.element_id)
                            if aim_id not in nodes_by_id:
                                nodes_by_id[aim_id] = {
                                    "id": aim_id,
                                    "name": n.get("name", ""),
                                    "labels": list(getattr(n, "labels", []) or []),
                                }
                    for rs in record["all_rels"] or []:
                        for r in rs:
                            rid = str(r.element_id)
                            if rid not in edges_by_id:
                                edges_by_id[rid] = {
                                    "id": rid,
                                    "type": r.type,
                                    "source": r.start_node.get("aim_id", ""),
                                    "target": r.end_node.get("aim_id", ""),
                                }
        return {"nodes": list(nodes_by_id.values()), "edges": list(edges_by_id.values())}


class _EntityExtractorAdapter:
    """Extracts entity seed aim_ids from a question via the LLM extractor
    + a name-lookup through Neo4j.
    """

    def __init__(self, extractor: Any, graph_client: Any) -> None:
        self._e = extractor
        self._g = graph_client

    async def extract(self, question: str) -> list[str]:
        result = await self._e.extract(text=question)
        entities = getattr(result, "entities", []) or []
        seeds: list[str] = []
        for e in entities:
            name = getattr(e, "name", None) or (e.get("name") if isinstance(e, dict) else None)
            if not name:
                continue
            aim_id = await self._g.lookup_entity_name(name)
            if aim_id:
                seeds.append(aim_id)
        return seeds


# ── Runner assembly ───────────────────────────────────────────────────────────


async def _build_runners() -> dict[str, Any]:
    import time
    import uuid as _uuid
    from aim.eval.baselines import (
        SystemResponse,
        _extract_citations,
        _timed,
        make_graph_only_runner,
        make_vector_only_runner,
    )
    from aim.llm.factory import get_embedding_provider, get_llm_provider
    from aim.vectordb.factory import get_vectordb_provider
    from aim.graph.neo4j_client import Neo4jClient
    from aim.extraction.llm_extractor import LLMExtractor
    from aim.agents.reasoning_agent import (
        _compiled_graph,
        _compute_recursion_limit,
        _run_branches_and_select,
    )
    from aim.agents.state import AgentState
    from aim.config import get_settings
    from aim.schemas.query import ReasoningDepth

    llm = get_llm_provider()
    embedder = _EmbedderAdapter(get_embedding_provider())
    vector_store = _VectorStoreAdapter(get_vectordb_provider())
    raw_graph = Neo4jClient()
    graph_client = _GraphClientAdapter(raw_graph)
    entity_extractor = _EntityExtractorAdapter(LLMExtractor(), raw_graph)

    async def aim_full_run(question: str) -> SystemResponse:
        async def _body() -> SystemResponse:
            t0 = time.perf_counter()
            settings = get_settings()
            initial = AgentState(
                query_id=_uuid.uuid4(),
                original_query=question,
                reasoning_depth=ReasoningDepth.STANDARD,
                access_principals=["public"],
                graph_search_enabled=True,
                vector_search_enabled=True,
            )
            recursion_limit = _compute_recursion_limit(settings.max_reasoning_loops)
            branch_count = max(1, min(int(settings.reasoning_branch_count), 3))
            if branch_count == 1:
                raw_final = await _compiled_graph.ainvoke(
                    initial, config={"recursion_limit": recursion_limit}
                )
                final = (
                    raw_final
                    if isinstance(raw_final, AgentState)
                    else AgentState.model_validate(raw_final)
                )
            else:
                final = await _run_branches_and_select(
                    initial,
                    recursion_limit,
                    branch_count,
                )
            answer = final.answer or ""
            # Pull aim_ids from the terminal AgentState — those live in
            # the same namespace as the seed and the gold_entities.
            graph_ids = tuple(
                e.entity_id for e in final.graph_entities if e.entity_id
            )
            vector_stable_ids_by_vector_id = {
                v.get("id"): (v.get("source_id") or v.get("aim_id") or v.get("id") or "")
                for v in final.vector_snippets
                if v.get("id")
            }
            vector_ids = tuple(
                v.get("source_id") or v.get("aim_id") or v.get("id") or ""
                for v in final.vector_snippets
            )
            retrieved = tuple(
                i for i in dict.fromkeys((*graph_ids, *vector_ids)) if i
            )
            # Cited from the answer's bracket citations or the citation_map.
            cited = []
            for ids in (final.citation_map or {}).values():
                cited.extend(ids)
            raw_cited_ids = tuple(dict.fromkeys(cited)) or _extract_citations(answer)

            def _stable_citation_ids(source_id: str) -> tuple[str, ...]:
                ref = final.sources.get(source_id)
                if ref is None:
                    return (source_id,) if source_id else ()
                meta = ref.metadata or {}
                stable: list[str] = []
                entity_id = meta.get("entity_id")
                if entity_id:
                    stable.append(str(entity_id))
                vector_id = meta.get("vector_id")
                if vector_id and vector_id in vector_stable_ids_by_vector_id:
                    stable.append(vector_stable_ids_by_vector_id[vector_id])
                for key in ("source_entity", "target_entity"):
                    value = meta.get(key)
                    if value:
                        stable.append(str(value))
                if not stable and source_id:
                    stable.append(source_id)
                return tuple(dict.fromkeys(i for i in stable if i))

            cited_ids = tuple(
                dict.fromkeys(
                    stable_id
                    for source_id in raw_cited_ids
                    for stable_id in _stable_citation_ids(source_id)
                )
            )
            return SystemResponse(
                answer=answer,
                retrieved_ids=retrieved,
                cited_ids=cited_ids,
                graph_path=graph_ids,
                latency_s=time.perf_counter() - t0,
                meta={
                    "sub_queries": len(final.sub_queries),
                    "branch_count": branch_count,
                },
            )
        return await _timed(_body)

    return {
        "vector_only": make_vector_only_runner(
            vector_store=vector_store, llm=llm, embedder=embedder, top_k=10,
        ),
        "graph_only": make_graph_only_runner(
            graph_client=graph_client,
            entity_extractor=entity_extractor,
            llm=llm,
            hops=2,
            limit=20,
        ),
        "aim_full": aim_full_run,
    }


# ── Main ──────────────────────────────────────────────────────────────────────


async def _run(fixture_path: str, out_path: str) -> int:
    from aim.eval.harness import run_eval_with_exit
    from aim.eval.report import render_report

    runners = await _build_runners()
    results = await run_eval_with_exit(
        fixture_path=fixture_path,
        runners=runners,
        judge=None,  # Likert judge optional; harness skips gracefully.
        max_concurrency_per_item=2,
    )
    # Write raw JSON alongside markdown for CI inspection.
    report_md = render_report(results)
    Path(out_path).write_text(report_md, encoding="utf-8")
    Path(out_path + ".json").write_text(
        json.dumps(results, default=str, indent=2), encoding="utf-8",
    )
    # Windows console may be cp1252 — encode/replace so the run never dies on print.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        print(report_md)
    except UnicodeEncodeError:
        print(report_md.encode("ascii", "replace").decode("ascii"))
    verdict = (results.get("exit_criterion") or {}).get("verdict", "UNKNOWN")
    return 0 if verdict == "PASS" else 1


def main() -> int:
    # Force UTF-8 on Windows console so structlog/agent steps containing
    # arrows (→, ↔) don't crash the LangGraph node with UnicodeEncodeError.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Run the A.2 live benchmark against the live stack.")
    ap.add_argument("--fixture", default="tests/eval/fixtures/ground_truth.yaml")
    ap.add_argument("--out", default="eval_report.md")
    args = ap.parse_args()
    return asyncio.run(_run(args.fixture, args.out))


if __name__ == "__main__":
    sys.exit(main())
