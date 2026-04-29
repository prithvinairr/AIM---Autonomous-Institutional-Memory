"""Phase 10 — query-conditioned edge / path scoring.

The pre-Phase-10 graph_searcher computed ``path_score`` as the plain mean of
feedback-adjusted ``_REL_TYPE_WEIGHTS``. Phase 10 generalises this to

    edge_score = α·query_affinity + β·feedback_weight + γ·inverse_degree

with the three weights summing to 1.0 and defaults ``(0, 1, 0)`` — so flag-off
the module is behaviour-equivalent to the current mean-of-feedback path.

These tests pin the pure math: no Neo4j, no embeddings, no I/O. Wire-in is
exercised by the graph_searcher tests elsewhere.
"""
from __future__ import annotations

import math

import pytest

from aim.agents.graph_scoring import (
    PathScoringWeights,
    inverse_degree_score,
    lexical_query_affinity,
    rerank_paths_for_query,
    score_edge,
    score_path,
    rank_paths,
)


# ── score_edge ───────────────────────────────────────────────────────────────

class TestScoreEdge:
    def test_defaults_collapse_to_feedback_only(self):
        """Default weights (0, 1, 0) — score_edge must equal the feedback
        weight alone. This guarantees a flag-off equivalence to the existing
        graph_searcher path."""
        w = PathScoringWeights()
        s = score_edge(
            feedback_weight=0.85,
            query_affinity=0.99,  # ignored at α=0
            inverse_degree=0.01,  # ignored at γ=0
            weights=w,
        )
        assert s == pytest.approx(0.85)

    def test_all_three_terms_contribute(self):
        w = PathScoringWeights(alpha=0.5, beta=0.3, gamma=0.2)
        s = score_edge(
            feedback_weight=1.0,
            query_affinity=0.4,
            inverse_degree=0.6,
            weights=w,
        )
        # 0.5*0.4 + 0.3*1.0 + 0.2*0.6 = 0.2 + 0.3 + 0.12 = 0.62
        assert s == pytest.approx(0.62)

    def test_score_is_clamped_to_unit_interval(self):
        """Degenerate inputs (>1 or <0) must clamp so downstream aggregation
        doesn't explode."""
        w = PathScoringWeights(alpha=1.0, beta=0.0, gamma=0.0)
        assert score_edge(
            feedback_weight=0.0, query_affinity=5.0, inverse_degree=0.0, weights=w
        ) == pytest.approx(1.0)
        assert score_edge(
            feedback_weight=0.0, query_affinity=-3.0, inverse_degree=0.0, weights=w
        ) == pytest.approx(0.0)

    def test_weights_must_sum_to_one_within_tolerance(self):
        """Sanity: weights that don't sum to ~1 are a caller bug. Pin the
        invariant so future refactors don't silently drift."""
        with pytest.raises(ValueError, match="sum to 1"):
            PathScoringWeights(alpha=0.5, beta=0.5, gamma=0.5)


# ── inverse_degree_score ─────────────────────────────────────────────────────

class TestInverseDegreeScore:
    def test_low_degree_endpoints_score_high(self):
        """An edge between two rare (degree=1) nodes must score notably
        higher than an edge between two hubs. Any realistic connected node
        has degree ≥ 1 so this is effectively the ceiling case."""
        rare = inverse_degree_score(src_degree=1, tgt_degree=1)
        assert rare > 0.5
        # Formula ceiling (both degrees zero) is exactly 1.0.
        assert inverse_degree_score(src_degree=0, tgt_degree=0) == pytest.approx(1.0)

    def test_high_degree_endpoints_score_low(self):
        """An edge between two hubs (degree 500 each) carries low signal —
        the hub dampening principle, applied at edge-score level."""
        s_hub = inverse_degree_score(src_degree=500, tgt_degree=500)
        s_rare = inverse_degree_score(src_degree=2, tgt_degree=2)
        assert s_hub < s_rare

    def test_zero_degree_is_handled(self):
        """A degree of 0 must not divide-by-zero."""
        s = inverse_degree_score(src_degree=0, tgt_degree=0)
        assert 0.0 <= s <= 1.0
        assert not math.isnan(s)
        assert not math.isinf(s)


# ── score_path ───────────────────────────────────────────────────────────────

class TestScorePath:
    def test_empty_path_returns_floor(self):
        """A path with no edges falls back to the documented floor (0.4) to
        match the pre-Phase-10 default."""
        assert score_path([]) == pytest.approx(0.4)

    def test_mean_aggregation(self):
        assert score_path([1.0, 0.5, 0.0], aggregation="mean") == pytest.approx(0.5)

    def test_product_aggregation(self):
        """Product aggregation penalises weak links heavily — a single 0.1
        edge drops the whole path score."""
        assert score_path([0.9, 0.1], aggregation="product") == pytest.approx(0.09)

    def test_unknown_aggregation_raises(self):
        with pytest.raises(ValueError):
            score_path([1.0], aggregation="geometric-mean-of-sines")


# ── rank_paths ───────────────────────────────────────────────────────────────

class TestRankPaths:
    def test_returns_paths_sorted_by_score_desc(self):
        p_low = {"id": "a", "edge_scores": [0.2, 0.3]}
        p_high = {"id": "b", "edge_scores": [0.9, 0.8]}
        p_mid = {"id": "c", "edge_scores": [0.5, 0.5]}
        ranked = rank_paths([p_low, p_high, p_mid], aggregation="mean")
        assert [p["id"] for p in ranked] == ["b", "c", "a"]
        # Caller sees the computed path_score on each element
        assert ranked[0]["path_score"] > ranked[-1]["path_score"]

    def test_top_k_truncates(self):
        paths = [{"id": str(i), "edge_scores": [i / 10]} for i in range(1, 11)]
        ranked = rank_paths(paths, aggregation="mean", top_k=3)
        assert len(ranked) == 3
        # Top-3 must be the three highest-scoring
        assert {p["id"] for p in ranked} == {"10", "9", "8"}

    def test_missing_edge_scores_falls_back_to_floor(self):
        """Defensive: a path dict without ``edge_scores`` must not crash;
        it gets the floor score instead."""
        paths = [{"id": "x"}]
        ranked = rank_paths(paths, aggregation="mean")
        assert ranked[0]["path_score"] == pytest.approx(0.4)


# ── Behaviour-equivalence to pre-Phase-10 formula ───────────────────────────
#
# Before Phase 10 the graph_searcher computed:
#     path_score = mean(adjusted_weights[rel_type] or 0.4)  for r in path_rels
# Phase 10 collapses to the same result when (α=0, β=1, γ=0) and aggregation
# is "mean". These tests pin that equivalence so flag-off deployments don't
# drift silently.

class TestBehaviourEquivalence:
    def test_default_weights_match_old_mean_formula(self):
        """Given three relationship weights, the Phase 10 pipeline must
        produce exactly the mean-of-weights that the old graph_searcher did."""
        adjusted = {"CAUSED_BY": 1.0, "OWNS": 0.8, "REFERENCES": 0.5}
        path_rels = [
            {"rel_type": "CAUSED_BY"},
            {"rel_type": "OWNS"},
            {"rel_type": "REFERENCES"},
        ]

        # Old formula:
        old = sum(adjusted.get(r["rel_type"], 0.4) for r in path_rels) / len(path_rels)

        # New pipeline with defaults:
        w = PathScoringWeights()  # (0, 1, 0)
        edge_scores = [
            score_edge(
                feedback_weight=adjusted.get(r["rel_type"], 0.4),
                query_affinity=0.0,
                inverse_degree=0.0,
                weights=w,
            )
            for r in path_rels
        ]
        new = score_path(edge_scores, aggregation="mean")

        assert new == pytest.approx(old)


class TestQueryAwarePathRerank:
    def test_approved_query_prefers_approval_path(self):
        approval_path = {
            "path_score": 0.8,
            "hops": 2,
            "path_nodes": [
                {"name": "ADR-001", "labels": ["Decision"]},
                {"name": "Sarah Chen", "labels": ["Person"]},
            ],
            "path_rels": [{"rel_type": "APPROVED_BY"}],
        }
        owner_path = {
            "path_score": 0.8,
            "hops": 2,
            "path_nodes": [
                {"name": "Auth Service", "labels": ["Service"]},
                {"name": "Alex Rivera", "labels": ["Person"]},
            ],
            "path_rels": [{"rel_type": "OWNS"}],
        }

        ranked = rerank_paths_for_query(
            "Who approved ADR-001?",
            [owner_path, approval_path],
        )

        assert ranked[0]["path_rels"][0]["rel_type"] == "APPROVED_BY"
        assert ranked[0]["path_query_affinity"] > ranked[1]["path_query_affinity"]

    def test_affinity_rewards_path_tokens_and_relationship_hints(self):
        path = {
            "path_nodes": [
                {"name": "ADR-003", "labels": ["Decision"]},
                {"name": "ADR-005", "labels": ["Decision"]},
            ],
            "path_rels": [{"rel_type": "SUPERSEDES"}],
        }

        score = lexical_query_affinity("Which ADR did ADR-003 supersede?", path)

        assert score > 0.25

    def test_unknown_rel_type_hits_floor_as_before(self):
        """The old code used 0.4 as the default for unknown rel_types. The
        new pipeline must preserve that floor when feedback_weight=0.4 is
        passed in."""
        w = PathScoringWeights()
        s = score_edge(
            feedback_weight=0.4, query_affinity=0.0, inverse_degree=0.0, weights=w
        )
        assert s == pytest.approx(0.4)

    def test_affinity_weighting_can_flip_path_ranking(self):
        """The whole point of Phase 10: a path through low-feedback
        relationship types but with strong query affinity must be able to
        out-rank a 'stronger' but off-topic path."""
        strong_feedback_weak_affinity = {
            "id": "strong_fb",
            "edge_scores": [
                score_edge(
                    feedback_weight=0.9,
                    query_affinity=0.1,
                    inverse_degree=0.0,
                    weights=PathScoringWeights(alpha=0.6, beta=0.4, gamma=0.0),
                ),
            ],
        }
        weak_feedback_strong_affinity = {
            "id": "strong_aff",
            "edge_scores": [
                score_edge(
                    feedback_weight=0.5,
                    query_affinity=0.95,
                    inverse_degree=0.0,
                    weights=PathScoringWeights(alpha=0.6, beta=0.4, gamma=0.0),
                ),
            ],
        }
        ranked = rank_paths(
            [strong_feedback_weak_affinity, weak_feedback_strong_affinity],
            aggregation="mean",
        )
        assert ranked[0]["id"] == "strong_aff"
