"""Pin tests for aim.eval.metrics — lock edge-case behaviour.

Pure-function tests: no IO, no mocks, no randomness.
"""
from __future__ import annotations

import math

from aim.eval import (
    aggregate_by_category,
    citation_accuracy,
    governed_claim_score,
    multi_hop_path_accuracy,
    ndcg_at_k,
    negative_rejection_rate,
)


# ── ndcg_at_k ──────────────────────────────────────────────────────────


def test_ndcg_empty_retrieved_returns_zero():
    assert ndcg_at_k([], ["a", "b"], k=10) == 0.0


def test_ndcg_empty_gold_returns_zero():
    assert ndcg_at_k(["a", "b"], [], k=10) == 0.0


def test_ndcg_perfect_order_returns_one():
    assert ndcg_at_k(["a", "b", "c"], ["a", "b", "c"], k=10) == 1.0


def test_ndcg_reverse_order_less_than_one():
    # All gold retrieved but in reversed order → DCG still = IDCG since
    # binary relevance; use a partial-overlap ordering instead so
    # positional discount kicks in.
    score = ndcg_at_k(["x", "y", "a"], ["a", "b", "c"], k=10)
    assert 0.0 < score < 1.0


def test_ndcg_single_hit_rank_one_is_one():
    assert ndcg_at_k(["a", "x", "y"], ["a"], k=10) == 1.0


def test_ndcg_k_truncates():
    # Gold is at rank 2 in retrieved. With k=1 it gets truncated → 0.0.
    assert ndcg_at_k(["x", "a"], ["a"], k=1) == 0.0


def test_ndcg_irrelevant_only_returns_zero():
    assert ndcg_at_k(["x", "y", "z"], ["a", "b"], k=10) == 0.0


def test_ndcg_partial_overlap_between_zero_and_one():
    score = ndcg_at_k(["a", "x", "b"], ["a", "b"], k=10)
    # DCG = 1/log2(2) + 1/log2(4) = 1 + 0.5 = 1.5
    # IDCG = 1/log2(2) + 1/log2(3) ≈ 1 + 0.6309 ≈ 1.6309
    assert math.isclose(score, 1.5 / (1.0 + 1.0 / math.log2(3)), rel_tol=1e-9)


# ── citation_accuracy ──────────────────────────────────────────────────


def test_citation_no_citations_empty_gold_returns_one():
    assert citation_accuracy([], []) == 1.0


def test_citation_no_citations_with_gold_returns_zero():
    assert citation_accuracy([], ["g1"]) == 0.0


def test_citation_cited_with_empty_gold_returns_zero():
    assert citation_accuracy(["c1"], []) == 0.0


def test_citation_all_cited_in_gold_returns_one():
    assert citation_accuracy(["a", "b"], ["a", "b", "c"]) == 1.0


def test_citation_half_in_gold_returns_half():
    assert citation_accuracy(["a", "x"], ["a", "b"]) == 0.5


# ── multi_hop_path_accuracy ────────────────────────────────────────────


def test_path_empty_gold_returns_zero():
    assert multi_hop_path_accuracy(["a", "b"], []) == 0.0


def test_path_empty_retrieved_returns_zero():
    assert multi_hop_path_accuracy([], ["a", "b"]) == 0.0


def test_path_exact_match_returns_one():
    assert multi_hop_path_accuracy(["a", "b", "c"], ["a", "b", "c"]) == 1.0


def test_path_lcs_with_detour_normalised_by_gold_length():
    # Retrieved visits all gold in order, with hub nodes interleaved.
    score = multi_hop_path_accuracy(
        ["a", "hub1", "b", "hub2", "c"], ["a", "b", "c"]
    )
    assert score == 1.0


def test_path_wrong_order_less_than_one():
    score = multi_hop_path_accuracy(["c", "b", "a"], ["a", "b", "c"])
    # LCS of "cba" and "abc" is length 1 → 1/3.
    assert score == 1 / 3


def test_path_partial_match():
    # Retrieved has a and c but missing b entirely.
    score = multi_hop_path_accuracy(["a", "x", "c"], ["a", "b", "c"])
    assert math.isclose(score, 2 / 3, rel_tol=1e-9)


# ── negative_rejection_rate ────────────────────────────────────────────


def test_negative_reject_empty_answer_is_one():
    assert negative_rejection_rate("") == 1.0


def test_negative_reject_dont_know_is_one():
    assert negative_rejection_rate("I don't know the answer.") == 1.0


def test_negative_reject_do_not_know_is_one():
    assert negative_rejection_rate("I do not know who that is.") == 1.0


def test_negative_reject_confident_answer_is_zero():
    assert negative_rejection_rate("The answer is X.") == 0.0


def test_negative_reject_case_insensitive():
    assert negative_rejection_rate("I DON'T KNOW") == 1.0


# ── governed_claim_score ───────────────────────────────────────────────


def test_governed_claim_empty_expected_returns_one():
    assert governed_claim_score([]) == 1.0


def test_governed_claim_missing_expected_returns_zero():
    assert governed_claim_score([], expected_active_fact_ids=["fact:a"]) == 0.0


def test_governed_claim_scores_truth_status_evidence_and_authority():
    facts = [
        {
            "fact_id": "fact:current",
            "truth_status": "active",
            "support_source_ids": ["src1"],
            "authority_score": 0.91,
        },
        {
            "fact_id": "fact:old",
            "truth_status": "superseded",
            "evidence_uri": "slack://C1/1",
            "authority_score": 0.61,
        },
    ]

    score = governed_claim_score(
        facts,
        expected_active_fact_ids=["fact:current"],
        expected_superseded_fact_ids=["fact:old"],
    )

    assert score == 1.0


def test_governed_claim_penalizes_unevidenced_claims():
    facts = [
        {
            "fact_id": "fact:a",
            "truth_status": "active",
            "authority_score": 0.8,
        }
    ]

    score = governed_claim_score(facts, expected_active_fact_ids=["fact:a"])

    assert score < 1.0


# ── aggregate_by_category ──────────────────────────────────────────────


def test_aggregate_empty_input_returns_empty_dict():
    assert aggregate_by_category([], {}) == {}


def test_aggregate_drops_items_without_category():
    result = aggregate_by_category(
        [("a", 1.0), ("b", 0.5), ("orphan", 0.0)],
        {"a": "single_hop", "b": "single_hop"},
    )
    assert "single_hop" in result
    assert math.isclose(result["single_hop"], 0.75, rel_tol=1e-9)
    # Orphan id is dropped, not silently averaged.
    assert len(result) == 1


def test_aggregate_multiple_items_per_category_averaged():
    result = aggregate_by_category(
        [("a", 1.0), ("b", 0.0), ("c", 0.5), ("d", 1.0)],
        {"a": "single_hop", "b": "single_hop", "c": "multi_hop", "d": "multi_hop"},
    )
    assert math.isclose(result["single_hop"], 0.5, rel_tol=1e-9)
    assert math.isclose(result["multi_hop"], 0.75, rel_tol=1e-9)
