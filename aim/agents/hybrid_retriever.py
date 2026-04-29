"""Phase γ.1 — retrieval fusion.

Today, graph search and vector search run as independent siblings in
the reasoning graph:

      decompose ─┬─► search_graph ─┐
                 └─► fetch_mcp ────┴─► retrieve_vectors ─► synthesize

Their outputs are concatenated in the synthesizer context. A vector
snippet whose source document is *the description of a highly-ranked
graph entity* gets no bonus from that fact. A graph entity that would
be reinforced by a confident vector hit about the same thing gets no
bonus either. The two retrievers pay the cost of running in parallel
and throw away the cross-signal.

This module implements the simplest useful fusion: **graph reranks
vector**. After both retrievals complete, vector snippets whose
metadata points at an ``entity_id`` that also appears in the graph
results get a score boost. Snippets where the graph agrees rise,
snippets where the graph is silent stay where they are.

The function is pure (no state mutation, no I/O) so it's trivially
testable and reusable. Wiring into the live agent lives in
``reasoning_agent.py`` behind the ``retrieval_fusion_mode`` config.

A second strategy, ``vector_seeds_graph`` (top-k vector hits become
additional graph seed entities for a second traversal pass), is
intentionally out of scope in this module — it requires re-entering
the graph retrieval path, which is a different kind of change.
"""
from __future__ import annotations

from typing import Any, Iterable


def fuse_by_graph_rerank(
    graph_entity_ids: Iterable[str],
    vector_snippets: list[dict[str, Any]],
    boost: float = 0.15,
) -> list[dict[str, Any]]:
    """Return vector snippets re-ordered so those matching the graph's
    retrieved entity set rise to the top.

    The scoring function is deliberately simple:

        fused_score = original_score + (boost if entity_matched else 0)

    No multiplicative interactions, no log-space ranking — a clear
    additive bump that's easy to tune and reason about. The original
    ``score`` is preserved on the returned dicts; an added
    ``fused_score`` makes the bump visible for debugging. The caller
    can persist the fused order without losing the original signal.

    Args:
        graph_entity_ids: ``entity_id`` values of entities returned by
            the current graph search.
        vector_snippets: the list as produced by ``retrieve_vectors``.
            Each dict is expected to carry a ``score`` float and a
            ``metadata`` dict that may contain ``entity_id``.
        boost: bonus applied to a snippet whose metadata matches a
            graph entity. Default 0.15 keeps the boost meaningful
            without steamrolling raw vector similarity.

    Returns:
        A new list of new dicts (not mutated in place), sorted by
        descending ``fused_score``. Input is not modified.
    """
    entity_set = {eid for eid in graph_entity_ids if eid}
    out: list[dict[str, Any]] = []
    for s in vector_snippets:
        fused = dict(s)
        raw_score = float(s.get("score", 0.0))
        md = s.get("metadata") or {}
        eid = md.get("entity_id")
        matched = bool(eid and eid in entity_set)
        fused["fused_score"] = raw_score + (boost if matched else 0.0)
        fused["graph_matched"] = matched
        out.append(fused)
    out.sort(key=lambda x: x["fused_score"], reverse=True)
    return out


def derive_seed_entity_ids(
    vector_snippets: list[dict[str, Any]],
    top_k: int = 5,
) -> list[str]:
    """Extract ``entity_id`` values from the top-k vector snippets by
    score, for use as additional seed nodes in a second graph-traversal
    pass (the ``vector_seeds_graph`` strategy).

    Returns a list of unique ``entity_id`` strings in descending score
    order. Snippets without an ``entity_id`` in metadata contribute
    nothing. Deduplicates while preserving first-seen ordering.

    Exposed for operators who want to implement ``vector_seeds_graph``
    outside of this module — the actual second-pass retrieval is
    deliberately not wired here.
    """
    seen: set[str] = set()
    out: list[str] = []
    ranked = sorted(
        vector_snippets,
        key=lambda s: float(s.get("score", 0.0)),
        reverse=True,
    )
    for s in ranked:
        if len(out) >= top_k:
            break
        md = s.get("metadata") or {}
        eid = md.get("entity_id")
        if not eid or eid in seen:
            continue
        seen.add(eid)
        out.append(eid)
    return out
