"""Pin tests for aim.eval.harness.recompute_exit_criterion.

Locks PASS/FAIL/UNKNOWN verdict boundaries against the A.2 exit criterion.
"""
from __future__ import annotations

from aim.eval.harness import recompute_exit_criterion


def _build_results(aim_items=None, vec_items=None):
    systems = {}
    if aim_items is not None:
        systems["aim_full"] = {"per_item": aim_items}
    if vec_items is not None:
        systems["vector_only"] = {"per_item": vec_items}
    return {"systems": systems}


def test_pass_case_multi_hop_20pp_single_hop_5pp():
    # Multi-hop: aim=0.80 vs vec=0.60 → +20pp.
    # Single-hop: aim=0.95 vs vec=0.90 → +5pp.
    cat_map = {"m1": "multi_hop", "s1": "single_hop"}
    results = _build_results(
        aim_items=[{"id": "m1", "ndcg": 0.80}, {"id": "s1", "ndcg": 0.95}],
        vec_items=[{"id": "m1", "ndcg": 0.60}, {"id": "s1", "ndcg": 0.90}],
    )
    out = recompute_exit_criterion(results, cat_map)
    assert out["verdict"] == "PASS"
    assert abs(out["multi_hop_delta_pp"] - 20.0) < 1e-6
    assert abs(out["single_hop_delta_pp"] - 5.0) < 1e-6


def test_fail_case_multi_hop_below_threshold():
    cat_map = {"m1": "multi_hop", "s1": "single_hop"}
    results = _build_results(
        aim_items=[{"id": "m1", "ndcg": 0.70}, {"id": "s1", "ndcg": 0.90}],
        vec_items=[{"id": "m1", "ndcg": 0.60}, {"id": "s1", "ndcg": 0.90}],
    )
    out = recompute_exit_criterion(results, cat_map)
    assert out["verdict"] == "FAIL"
    assert "multi-hop" in out["rationale"]


def test_fail_case_single_hop_regression():
    cat_map = {"m1": "multi_hop", "s1": "single_hop"}
    results = _build_results(
        aim_items=[{"id": "m1", "ndcg": 0.80}, {"id": "s1", "ndcg": 0.85}],
        vec_items=[{"id": "m1", "ndcg": 0.60}, {"id": "s1", "ndcg": 0.90}],
    )
    out = recompute_exit_criterion(results, cat_map)
    assert out["verdict"] == "FAIL"
    assert "single-hop" in out["rationale"]


def test_unknown_when_no_aim_full():
    cat_map = {"s1": "single_hop"}
    results = _build_results(vec_items=[{"id": "s1", "ndcg": 0.5}])
    out = recompute_exit_criterion(results, cat_map)
    assert out["verdict"] == "UNKNOWN"


def test_unknown_when_no_vector_only():
    cat_map = {"s1": "single_hop"}
    results = _build_results(aim_items=[{"id": "s1", "ndcg": 0.5}])
    out = recompute_exit_criterion(results, cat_map)
    assert out["verdict"] == "UNKNOWN"


def test_exact_threshold_is_pass():
    # multi-hop Δ = exactly +15pp, single-hop Δ = exactly 0pp → PASS (inclusive).
    cat_map = {"m1": "multi_hop", "s1": "single_hop"}
    results = _build_results(
        aim_items=[{"id": "m1", "ndcg": 0.75}, {"id": "s1", "ndcg": 0.80}],
        vec_items=[{"id": "m1", "ndcg": 0.60}, {"id": "s1", "ndcg": 0.80}],
    )
    out = recompute_exit_criterion(results, cat_map)
    assert out["verdict"] == "PASS"
    assert abs(out["multi_hop_delta_pp"] - 15.0) < 1e-6
    assert abs(out["single_hop_delta_pp"] - 0.0) < 1e-6
