"""Phase γ.2 — branch-and-select scoring primitives.

The reasoning loop today is linear: one retrieval, one synthesis, one
evaluation, and on low scores it reloops (same code path, possibly
deeper). Tree-of-thought style branching generalises this: for a given
sub-query, run *multiple* candidate answers through the pipeline in
parallel — each with a different retrieval strategy (vector-only,
graph-only, hybrid/fused) — then pick the winner by evaluator score
rather than committing up-front to one recipe.

This module ships the *scoring and selection* half of that idea as pure,
trivially-testable functions. The actual fan-out (spawning N pipeline
branches and gathering their results) is a LangGraph-shape change and
lives outside this module — gated behind ``settings.reasoning_branch_count``
(default ``1`` = current behaviour, zero-cost) so the primitive can be
wired in incrementally.

Why ship the scoring half first
-------------------------------
A branch selector without a deterministic, explainable score is a
black-box coin flip. By pinning the score function here, the eventual
wire-in becomes a wiring task, not a design task — we already know how
candidates are ranked and why.

The score is intentionally the same heuristic the evaluator already
uses (citation coverage, query coverage, confidence, length floor), so
selection is consistent with re-loop decisions; a branch that would be
accepted by the evaluator on its own is the kind of branch we want the
selector to prefer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BranchCandidate:
    """A single end-to-end candidate answer produced by one branch of
    the reasoning fan-out.

    Only the fields needed for scoring are required; the full
    :class:`AgentState` or :class:`QueryResponse` is not, because the
    selector deliberately avoids coupling to the agent state schema (so
    it stays unit-testable without constructing a full AgentState).
    """

    branch_id: str
    answer_text: str
    # Source IDs that the answer actually cited (deduplicated).
    cited_source_ids: tuple[str, ...]
    # Total number of sources retrieved for this branch.
    total_sources: int
    # Sub-queries that returned at least one source / total sub-queries.
    covered_sub_queries: int
    total_sub_queries: int
    # Synthesizer-reported overall confidence, in [0, 1].
    confidence: float
    # Free-form metadata for debugging (strategy name, timings, etc.).
    metadata: dict[str, Any] = field(default_factory=dict)


# Weights mirror the evaluator so selection stays consistent with
# reloop accept/reject thresholds. Kept in sync manually — low churn.
_W_CITATION = 0.30
_W_QUERY_COV = 0.30
_W_CONFIDENCE = 0.25
_W_LENGTH = 0.15

# Answers shorter than this are penalised — typically a synthesizer
# that hit a safety-refusal or a retrieval miss.
_MIN_USEFUL_LENGTH = 120


def score_candidate(c: BranchCandidate) -> float:
    """Deterministic heuristic score in [0, 1] — higher is better.

    Mirrors :func:`aim.agents.nodes.evaluator.evaluate_answer` (heuristic
    mode) so a candidate the evaluator would accept on its own scores
    above ``reloop_threshold`` here too.
    """
    if c.total_sources <= 0:
        citation_cov = 0.0
    else:
        citation_cov = min(len(set(c.cited_source_ids)) / c.total_sources, 1.0)

    if c.total_sub_queries <= 0:
        query_cov = 1.0
    else:
        query_cov = c.covered_sub_queries / c.total_sub_queries

    conf = max(0.0, min(c.confidence, 1.0))
    length_score = min(len(c.answer_text) / _MIN_USEFUL_LENGTH, 1.0)

    return (
        _W_CITATION * citation_cov
        + _W_QUERY_COV * query_cov
        + _W_CONFIDENCE * conf
        + _W_LENGTH * length_score
    )


def select_best(
    candidates: list[BranchCandidate],
) -> tuple[BranchCandidate, list[tuple[str, float]]]:
    """Pick the highest-scoring candidate; return it plus a (branch_id,
    score) ranking for observability.

    Ties are broken by input order (the stable ``sorted`` pass keeps
    earlier branches ahead on exact ties). On an empty list raises
    :class:`ValueError` — callers should never invoke selection with no
    branches; that's a programming error, not a runtime fallback.
    """
    if not candidates:
        raise ValueError("select_best requires at least one candidate")
    ranked = sorted(
        ((c, score_candidate(c)) for c in candidates),
        key=lambda pair: pair[1],
        reverse=True,
    )
    winner, _ = ranked[0]
    scoreboard = [(c.branch_id, s) for c, s in ranked]
    return winner, scoreboard


# ── δ.3 Move 3 — LLM tiebreaker ───────────────────────────────────────────────
# The plain heuristic ``select_best`` is fast and deterministic, which is
# what 90%+ of fan-outs need: one branch scores clearly higher and gets
# picked. The remaining ~10% are statistical ties — two branches with
# near-identical heuristic scores where picking either is a coin flip.
#
# Calling the LLM on *every* selection would turn branching from a cheap
# parallelism win into a per-query cost multiplier. Instead, the
# ``llm_tiebreaker`` mode fires the LLM only when the spread between the
# top-two candidates is below a configurable threshold — the cost is
# bounded (~one extra judge call when it matters, zero when it doesn't)
# and the judge's vote is *advisory*: if it raises, we fall back to the
# heuristic winner rather than crashing the query.

# A judge takes the top-k candidates (by heuristic score, descending) and
# returns the chosen branch_id. Declared as a Callable-returning-Awaitable
# so tests can pass a plain lambda wrapping a coroutine.
TiebreakerJudge = Callable[[list[BranchCandidate]], Awaitable[str]]


async def select_best_with_tiebreaker(
    candidates: list[BranchCandidate],
    *,
    threshold: float,
    judge: TiebreakerJudge | None,
) -> tuple[BranchCandidate, list[tuple[str, float]], bool]:
    """Heuristic select_best, but ask an LLM judge on near-ties.

    Args:
        candidates: non-empty list of branch candidates.
        threshold: spread (in [0,1]) below which the judge is invoked.
            A spread of exactly ``threshold`` is NOT considered a tie —
            the comparison is strict ``<`` so a threshold of 0.0 disables
            the judge entirely and the call is equivalent to
            :func:`select_best`.
        judge: async callable that picks a winner from the tied top-two.
            May be ``None``, in which case the heuristic winner is used
            unchanged (lets callers cheaply probe the "would the judge
            fire?" question without actually paying for it).

    Returns:
        Tuple of ``(winner, scoreboard, judge_invoked)``. ``judge_invoked``
        is ``True`` only when the judge was actually called *and*
        returned without raising — callers use it to record telemetry
        and separate "heuristic-certain" wins from "LLM-picked" ones.
    """
    if not candidates:
        raise ValueError("select_best_with_tiebreaker requires at least one candidate")

    ranked = sorted(
        ((c, score_candidate(c)) for c in candidates),
        key=lambda pair: pair[1],
        reverse=True,
    )
    scoreboard = [(c.branch_id, s) for c, s in ranked]
    heuristic_winner, top_score = ranked[0]

    # Single candidate or no judge configured → nothing to adjudicate.
    if len(ranked) < 2 or judge is None:
        return heuristic_winner, scoreboard, False

    runner_up_score = ranked[1][1]
    spread = top_score - runner_up_score

    # Clear winner — skip the LLM call entirely. This is the hot path
    # and must stay zero-cost.
    if spread >= threshold:
        return heuristic_winner, scoreboard, False

    # Near-tie: collect everyone within ``threshold`` of the top so the
    # judge sees all genuinely-close candidates (not just top-two — a
    # three-way tie should be judged as such, not two calls in a row).
    contenders = [c for c, s in ranked if (top_score - s) < threshold]

    try:
        chosen_id = await judge(contenders)
    except Exception as exc:  # noqa: BLE001 — judge is best-effort
        # Fail soft: log, return heuristic winner. Never let a flaky
        # tiebreaker take down the query.
        log.warning(
            "branch_selector.tiebreaker_failed",
            extra={"error": str(exc), "spread": spread},
        )
        return heuristic_winner, scoreboard, False

    # Judge may return an unknown id (hallucination or network blip);
    # in that case we also fall back to the heuristic winner.
    chosen = next(
        (c for c in contenders if c.branch_id == chosen_id),
        None,
    )
    if chosen is None:
        log.warning(
            "branch_selector.tiebreaker_unknown_id",
            extra={"chosen_id": chosen_id, "valid_ids": [c.branch_id for c in contenders]},
        )
        return heuristic_winner, scoreboard, False

    return chosen, scoreboard, True
