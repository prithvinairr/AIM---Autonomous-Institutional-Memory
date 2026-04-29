"""Pure-function eval metrics. Zero IO, zero config.

Every metric takes simple primitives (lists of ids, strings, numbers) so
it's unit-testable without a live stack. The orchestration layer
(``harness.py``) projects system responses into these shapes.

Four metrics live here:

* ``ndcg_at_k`` — retrieval quality, standard IR metric. Tells us whether
  the *right* sources were found, regardless of what the LLM did with them.
* ``citation_accuracy`` — of the sources the LLM cited, how many were
  actually in the gold set. Measures the LLM's grounding discipline.
* ``multi_hop_path_accuracy`` — did the retrieved graph path match the
  gold path entity-for-entity. Specific to graph retrieval; meaningless
  for vector-only baselines (returns 0.0 in that case — a known limit).
* ``negative_rejection_rate`` — on questions with no corpus answer, did
  the system say "I don't know" (good) or hallucinate (bad).

All return floats in [0, 1]. All handle empty inputs deterministically
(return 0.0, never raise) so a completely broken system still gets a
report rendered instead of crashing the whole eval.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


def ndcg_at_k(retrieved_ids: Sequence[str],
              gold_ids: Sequence[str],
              k: int = 10) -> float:
    """Normalized Discounted Cumulative Gain at rank k.

    Binary relevance: an id is relevant iff it's in gold_ids. We use
    binary rather than graded because AIM returns identity matches from
    entity extraction, not similarity scores we could threshold into
    graded relevance.

    Returns 0.0 if gold is empty (no signal to measure) or retrieved is
    empty (nothing to score). A system that returns the right id at
    rank 1 gets 1.0; at rank 10 gets ~0.36; not at all gets 0.0.
    """
    if not gold_ids or not retrieved_ids:
        return 0.0
    gold_set = set(gold_ids)

    def _dcg(ids: Sequence[str]) -> float:
        return sum(
            (1.0 if rid in gold_set else 0.0) / math.log2(i + 2)
            for i, rid in enumerate(ids[:k])
        )

    ideal_hits = min(len(gold_set), k)
    # IDCG is what you'd get if every gold hit were at the top.
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    if idcg == 0.0:
        return 0.0
    return _dcg(retrieved_ids) / idcg


def citation_accuracy(cited_ids: Sequence[str],
                      gold_sources: Sequence[str]) -> float:
    """Fraction of cited sources that are in the gold set.

    Measures grounding discipline — does the LLM cite things that
    actually support the answer? Returns 1.0 if nothing was cited and
    the gold set is empty (nothing claimed, nothing wrong). Returns 0.0
    if the LLM cited sources but none matched gold.

    Explicitly NOT recall — we aren't asking "did it cite everything it
    could have", we're asking "of what it did cite, how much was right".
    Recall is a separate metric; most ops pain comes from the precision
    side (over-claiming), so that's what this pins.
    """
    if not cited_ids:
        # No citations. Either there was nothing to cite (gold empty → fine)
        # or the system refused to cite (gold non-empty → 0.0).
        return 1.0 if not gold_sources else 0.0
    if not gold_sources:
        # System cited sources but eval has no gold set for this item.
        # Treat as neutral — returning 0.0 would penalise items whose
        # fixture just doesn't enumerate sources.
        return 0.0
    gold_set = set(gold_sources)
    hits = sum(1 for cid in cited_ids if cid in gold_set)
    return hits / len(cited_ids)


def multi_hop_path_accuracy(retrieved_path: Sequence[str],
                            gold_path: Sequence[str]) -> float:
    """How well does the retrieved traversal match the gold path.

    Scoring strategy: length-normalized longest-common-subsequence. A
    retrieved path that visits the gold entities in the right order (even
    with detours) scores high; a path that visits them out of order or
    misses scores low.

    Why LCS and not exact match: AIM's graph_searcher may traverse
    intermediate hub nodes the gold author didn't think to enumerate.
    Exact-match would unfairly penalise this. LCS rewards "the right
    backbone was found" even if the path has extra vertebrae.

    Returns 0.0 if gold_path is empty (the item isn't a multi-hop
    question) so this metric is safe to call on every item — single-hop
    items just don't contribute.
    """
    if not gold_path or not retrieved_path:
        return 0.0

    # Standard LCS DP. Cost O(m*n); fine for paths of realistic length (<50).
    m, n = len(retrieved_path), len(gold_path)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if retrieved_path[i - 1] == gold_path[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    lcs = dp[m][n]
    # Normalise by gold length — we care whether the gold backbone was
    # found, not whether the retrieved path happens to be short.
    return lcs / len(gold_path)


def negative_rejection_rate(answer: str) -> float:
    """1.0 if the system said "I don't know" on a negative question, else 0.0.

    Deliberately a cheap keyword check — a stronger version would use
    the Likert judge, but this is the no-cost-no-LLM baseline used for
    per-system screening. The keyword list is intentionally broad; a
    false-positive here (treating a confident answer as a rejection) is
    caught by the judge in the next stage.
    """
    if not answer:
        return 1.0  # empty answer = rejection
    needles = (
        "don't know", "do not know", "unknown", "no information",
        "not found", "cannot find", "no data", "no record", "not in",
        "not aware", "no evidence", "unable to find",
    )
    low = answer.lower()
    return 1.0 if any(n in low for n in needles) else 0.0


def _field(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def governed_claim_score(
    facts: Sequence[Any],
    *,
    expected_active_fact_ids: Sequence[str] = (),
    expected_superseded_fact_ids: Sequence[str] = (),
    require_evidence: bool = True,
) -> float:
    """Score institutional-memory governance in returned provenance.

    This measures the part vanilla RAG does not have: durable claims with
    evidence, authority, and truth-maintenance status. It accepts dicts or
    Pydantic objects so the harness can feed it raw API JSON or typed schemas.
    """
    if not facts:
        return 0.0 if (expected_active_fact_ids or expected_superseded_fact_ids) else 1.0

    by_id = {str(_field(fact, "fact_id", "")): fact for fact in facts}
    components: list[float] = []

    if expected_active_fact_ids:
        hits = sum(
            1
            for fact_id in expected_active_fact_ids
            if str(_field(by_id.get(fact_id, {}), "truth_status", "")) == "active"
        )
        components.append(hits / len(expected_active_fact_ids))

    if expected_superseded_fact_ids:
        hits = sum(
            1
            for fact_id in expected_superseded_fact_ids
            if str(_field(by_id.get(fact_id, {}), "truth_status", "")) == "superseded"
        )
        components.append(hits / len(expected_superseded_fact_ids))

    if require_evidence:
        evidenced = 0
        for fact in facts:
            support = _field(fact, "support_source_ids", []) or []
            if support or _field(fact, "evidence_uri") or _field(fact, "evidence_artifact_id"):
                evidenced += 1
        components.append(evidenced / len(facts))

    authority_scored = sum(
        1 for fact in facts
        if float(_field(fact, "authority_score", 0.0) or 0.0) > 0.0
    )
    components.append(authority_scored / len(facts))

    return sum(components) / len(components) if components else 0.0


def aggregate_by_category(
    per_item: list[tuple[str, float]],
    categories: dict[str, str],
) -> dict[str, float]:
    """Average a per-item metric within each category.

    ``per_item`` is ``[(item_id, score), ...]``; ``categories`` maps
    item_id → category string. Items with no category mapping are
    dropped (caller error, not a silent averaging bug).

    Returns ``{"single_hop": 0.82, "multi_hop": 0.64, ...}``. Missing
    categories get 0.0 so downstream consumers never KeyError.
    """
    buckets: dict[str, list[float]] = {}
    for item_id, score in per_item:
        cat = categories.get(item_id)
        if cat is None:
            continue
        buckets.setdefault(cat, []).append(score)
    return {c: (sum(vs) / len(vs) if vs else 0.0) for c, vs in buckets.items()}
