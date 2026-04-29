"""A.2 eval orchestrator — ties loader → runners → metrics → judge → report.

This is the one non-pure piece in ``aim.eval`` that's still pure *enough*
to unit-test with fake runners. The harness never talks to Neo4j /
Pinecone / the LLM directly — it calls injected ``Runner`` callables
and an injected judge callable. Live wiring lives in the CLI shim at
the bottom of this file (``python -m aim.eval.harness``).

High-level flow per item:

    1. Call every runner on the question in parallel (``asyncio.gather``).
    2. Project runner output into metric-ready shapes.
    3. Compute metrics per-item.
    4. Optionally call the Likert judge on each (question, answer) pair.

Aggregation:

    * Per category (single_hop / multi_hop / negative / ambiguous) via
      ``aggregate_by_category`` so the report can show the multi-hop
      delta separately — that's the specific claim in the plan.
    * Overall = unweighted mean across all items. We don't weight by
      category size because a fixture skewed 95% single-hop would then
      hide a multi-hop regression.

Latency is a p50 (median) across items, not a mean, to match how the
A.1 load test reports latency.

Deliberate non-goals of this file:

* No retry logic. A runner that flakes shows up as an ``error`` on
  the response; the metrics treat it as zero. Retries belong in the
  runners themselves, not the harness.
* No concurrency limits. Runners are called per-item sequentially
  (parallel across *systems* per item, but not across items) because
  most rate-limit pain is at the LLM layer and runners hit that in
  series naturally.
"""
from __future__ import annotations

import asyncio
import logging
import statistics
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from aim.eval.baselines import Runner, SystemResponse
from aim.eval.loader import (
    GroundTruthItem,
    category_breakdown,
    hop_depth_breakdown,
    load_ground_truth,
)
from aim.eval.metrics import (
    aggregate_by_category,
    citation_accuracy,
    multi_hop_path_accuracy,
    ndcg_at_k,
    negative_rejection_rate,
)

log = logging.getLogger(__name__)


# Judge signature: (question, gold_answer, system_answer) → 1..5 or None.
JudgeFn = Callable[[str, str | None, str], Awaitable[int | None]]


# ── Per-item score bundle ──────────────────────────────────────────────


@dataclass(frozen=True)
class ItemScore:
    """Per-item per-system scores. All floats in [0, 1] except likert.

    ``likert`` is 1–5 (or None if the judge was skipped or errored).
    """

    item_id: str
    system: str
    ndcg: float
    cite: float
    path: float
    reject: float
    likert: int | None
    latency_s: float
    error: str | None = None


# ── Main entry point ───────────────────────────────────────────────────


async def run_eval(
    *,
    fixture_path: str,
    runners: dict[str, Runner],
    judge: JudgeFn | None = None,
    max_concurrency_per_item: int = 4,
) -> dict[str, Any]:
    """Run every runner on every fixture item and aggregate.

    ``runners`` maps system-name → async callable. ``judge`` is optional
    — if None, Likert is reported as None everywhere and the report
    renders "—" for that column. Useful for fast smoke runs where you
    don't want to pay for judge inference.

    Returns the results dict shape documented in ``report.py``.
    """
    items = load_ground_truth(fixture_path)
    fixture_summary = {
        "path": str(fixture_path),
        "counts": category_breakdown(items),
        "hop_depths": hop_depth_breakdown(items),
    }

    # category lookup used by aggregate_by_category.
    category_map = {it.id: it.category for it in items}

    per_system_scores: dict[str, list[ItemScore]] = {name: [] for name in runners}

    sem = asyncio.Semaphore(max_concurrency_per_item)

    async def _run_one(item: GroundTruthItem) -> dict[str, SystemResponse]:
        async def _call(name: str, runner: Runner) -> tuple[str, SystemResponse]:
            async with sem:
                resp = await runner(item.question)
            return name, resp

        pairs = await asyncio.gather(
            *(_call(n, r) for n, r in runners.items())
        )
        return dict(pairs)

    for item in items:
        responses = await _run_one(item)
        for system_name, resp in responses.items():
            score = await _score_one(item, system_name, resp, judge)
            per_system_scores[system_name].append(score)

    # Shape into report dict.
    systems_block: dict[str, Any] = {}
    for name, scores in per_system_scores.items():
        systems_block[name] = _aggregate_system(scores, category_map)

    exit_block = _compute_exit_criterion(per_system_scores)

    return {
        "fixture": fixture_summary,
        "systems": systems_block,
        "exit_criterion": exit_block,
    }


# ── Per-item scoring ───────────────────────────────────────────────────


async def _score_one(
    item: GroundTruthItem,
    system_name: str,
    resp: SystemResponse,
    judge: JudgeFn | None,
) -> ItemScore:
    """Compute all metrics for one (item, system) pair.

    Errors are flowed through: metrics see empty sequences and return
    0.0, which is the correct "system failed this item" signal.
    """
    # Negative items measure rejection, not retrieval — but we still
    # compute ndcg/cite/path so the report can show "system found
    # something when it shouldn't have".
    ndcg = ndcg_at_k(resp.retrieved_ids, item.gold_entities, k=10)
    # Older A.2 fixtures often omit source-level gold labels. Fall back to
    # stable entity ids so citation precision measures grounding, not whether
    # the model happened to abstain from citing an item with empty gold_sources.
    citation_gold = item.gold_sources or item.gold_entities
    cite = citation_accuracy(resp.cited_ids, citation_gold)
    path = multi_hop_path_accuracy(resp.graph_path, item.gold_path)
    reject = negative_rejection_rate(resp.answer) if item.is_negative else 0.0

    likert: int | None = None
    if judge is not None and not resp.error:
        try:
            likert = await judge(item.question, item.gold_answer, resp.answer)
        except Exception as exc:  # noqa: BLE001
            log.warning("judge errored on %s/%s: %s", item.id, system_name, exc)
            likert = None

    return ItemScore(
        item_id=item.id,
        system=system_name,
        ndcg=ndcg,
        cite=cite,
        path=path,
        reject=reject,
        likert=likert,
        latency_s=resp.latency_s,
        error=resp.error,
    )


# ── Aggregation ────────────────────────────────────────────────────────


def _aggregate_system(
    scores: list[ItemScore],
    category_map: dict[str, str],
) -> dict[str, Any]:
    """Roll up one system's per-item scores into overall + by-category."""
    if not scores:
        return {"per_item": [], "by_category": {}, "overall": {}}

    # Flatten for report rendering.
    per_item = [
        {
            "id": s.item_id,
            "ndcg": s.ndcg,
            "cite": s.cite,
            "path": s.path,
            "reject": s.reject,
            "likert": s.likert,
            "latency_s": s.latency_s,
            "error": s.error,
        }
        for s in scores
    ]

    by_category: dict[str, dict[str, float]] = {}
    for metric in ("ndcg", "cite", "path", "reject", "latency_s"):
        pairs = [(s.item_id, getattr(s, metric)) for s in scores]
        bucketed = aggregate_by_category(pairs, category_map)
        for cat, v in bucketed.items():
            by_category.setdefault(cat, {})[metric] = v

    # Likert: separate path because None values are excluded from means.
    likert_pairs = [
        (s.item_id, float(s.likert)) for s in scores if s.likert is not None
    ]
    likert_by_cat = aggregate_by_category(likert_pairs, category_map)
    for cat, v in likert_by_cat.items():
        by_category.setdefault(cat, {})["likert"] = v

    overall = {
        "ndcg": _mean(s.ndcg for s in scores),
        "cite": _mean(s.cite for s in scores),
        "path": _mean(s.path for s in scores),
        "reject": _mean(
            s.reject for s in scores if category_map.get(s.item_id) == "negative"
        ),
        "likert": _mean(
            float(s.likert) for s in scores if s.likert is not None
        ),
        # p50 latency — matches A.1 reporting convention.
        "latency_s": _median(s.latency_s for s in scores),
    }
    return {"per_item": per_item, "by_category": by_category, "overall": overall}


def _mean(values) -> float:
    vs = [v for v in values if v is not None]
    return sum(vs) / len(vs) if vs else 0.0


def _median(values) -> float:
    vs = [v for v in values if v is not None]
    return statistics.median(vs) if vs else 0.0


# ── Exit criterion (the A.2 gate) ──────────────────────────────────────


def _compute_exit_criterion(
    per_system_scores: dict[str, list[ItemScore]],
) -> dict[str, Any]:
    """Decide PASS/FAIL against the customer plan A.2 target.

    Target: ``aim_full`` beats ``vector_only`` on multi-hop NDCG by
    ≥15pp, AND ties or wins (≥0pp) on single-hop.

    Returns an UNKNOWN verdict if either baseline is missing — we
    don't want a partial run to produce a false PASS.
    """
    if "aim_full" not in per_system_scores or "vector_only" not in per_system_scores:
        return {
            "multi_hop_delta_pp": None,
            "single_hop_delta_pp": None,
            "verdict": "UNKNOWN",
            "rationale": (
                "Need both aim_full and vector_only runners to compute delta. "
                "Found: " + ", ".join(sorted(per_system_scores.keys()))
            ),
        }

    def _cat_mean(name: str, category: str) -> float | None:
        scores = per_system_scores[name]
        vs = [s.ndcg for s in scores if _category_of(s, per_system_scores) == category]
        return sum(vs) / len(vs) if vs else None

    # We need a category lookup; rebuild from item ids using one of the
    # systems (every system saw the same fixture, so any will do).
    any_scores = per_system_scores["vector_only"]
    # Hack: we don't have the loader's category map here, so we need
    # the caller to thread it. Simpler: walk items by id via the
    # scores' error path — but we don't keep category on ItemScore.
    # Accept the limitation and compute via raw means; the caller
    # builds a category map from the fixture and passes it via the
    # closure below if needed. For now, approximate: treat all items
    # as a flat pool and compute an overall delta, plus note the
    # limitation.
    aim_overall = _mean(s.ndcg for s in per_system_scores["aim_full"])
    vec_overall = _mean(s.ndcg for s in per_system_scores["vector_only"])
    overall_delta_pp = (aim_overall - vec_overall) * 100

    return {
        # These are populated by the caller via recompute_exit_criterion
        # once the category map is threaded through — the harness's
        # top-level run_eval handles that.
        "multi_hop_delta_pp": None,
        "single_hop_delta_pp": None,
        "overall_ndcg_delta_pp": overall_delta_pp,
        "verdict": "UNKNOWN",
        "rationale": (
            "Per-category deltas not available in this code path; run via "
            "run_eval which threads the category map. Overall NDCG delta: "
            f"{overall_delta_pp:+.1f}pp."
        ),
    }


def _category_of(
    _score: ItemScore, _per_system: dict[str, list[ItemScore]]
) -> str:  # pragma: no cover — replaced by closure in run_eval
    return ""


def recompute_exit_criterion(
    results: dict[str, Any],
    category_map: dict[str, str],
) -> dict[str, Any]:
    """Post-hoc exit block using category info the top-level flow has.

    Separate from ``_compute_exit_criterion`` so the harness can call it
    after building the systems block (which carries per_item with ids),
    and tests can exercise it without spinning up runners.
    """
    systems = results.get("systems", {})
    if "aim_full" not in systems or "vector_only" not in systems:
        return {
            "multi_hop_delta_pp": None,
            "single_hop_delta_pp": None,
            "verdict": "UNKNOWN",
            "rationale": "Both aim_full and vector_only are required.",
        }

    def _cat_ndcg(system: str, category: str) -> float | None:
        items = systems[system].get("per_item", [])
        vs = [
            it["ndcg"] for it in items
            if category_map.get(it["id"]) == category
        ]
        return sum(vs) / len(vs) if vs else None

    mh_aim = _cat_ndcg("aim_full", "multi_hop")
    mh_vec = _cat_ndcg("vector_only", "multi_hop")
    sh_aim = _cat_ndcg("aim_full", "single_hop")
    sh_vec = _cat_ndcg("vector_only", "single_hop")

    mh_delta_pp = (mh_aim - mh_vec) * 100 if (mh_aim is not None and mh_vec is not None) else None
    sh_delta_pp = (sh_aim - sh_vec) * 100 if (sh_aim is not None and sh_vec is not None) else None

    if mh_delta_pp is None or sh_delta_pp is None:
        verdict = "UNKNOWN"
        rationale = "Missing single-hop or multi-hop items in fixture."
    elif mh_delta_pp >= 15.0 and sh_delta_pp >= 0.0:
        verdict = "PASS"
        rationale = (
            f"AIM full beats vector_only on multi-hop by {mh_delta_pp:+.1f}pp "
            f"(≥15pp required) and ties/wins single-hop by {sh_delta_pp:+.1f}pp."
        )
    else:
        verdict = "FAIL"
        reasons = []
        if mh_delta_pp < 15.0:
            reasons.append(f"multi-hop delta {mh_delta_pp:+.1f}pp < 15pp target")
        if sh_delta_pp < 0.0:
            reasons.append(f"single-hop regression {sh_delta_pp:+.1f}pp")
        rationale = "; ".join(reasons) or "exit criterion not met"

    return {
        "multi_hop_delta_pp": mh_delta_pp,
        "single_hop_delta_pp": sh_delta_pp,
        "verdict": verdict,
        "rationale": rationale,
    }


# Wire recompute_exit_criterion into run_eval's output.  We keep this
# as a separate function (not inlined) so tests can call it on canned
# results dicts without constructing runners.
_original_run_eval = run_eval


async def run_eval_with_exit(
    *,
    fixture_path: str,
    runners: dict[str, Runner],
    judge: JudgeFn | None = None,
    max_concurrency_per_item: int = 4,
) -> dict[str, Any]:
    """run_eval + post-hoc exit criterion with per-category deltas.

    Preferred entry point for the CLI shim. ``run_eval`` is kept as a
    lower-level primitive so tests can inspect the pre-exit shape.
    """
    results = await _original_run_eval(
        fixture_path=fixture_path,
        runners=runners,
        judge=judge,
        max_concurrency_per_item=max_concurrency_per_item,
    )
    items = load_ground_truth(fixture_path)
    category_map = {it.id: it.category for it in items}
    results["exit_criterion"] = recompute_exit_criterion(results, category_map)
    return results
