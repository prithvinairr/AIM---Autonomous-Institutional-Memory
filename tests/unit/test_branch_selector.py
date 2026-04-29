"""Phase γ.2 — branch-and-select scoring primitives.

Pins the scoring + selection contract of
``aim.agents.branch_selector``:

* ``score_candidate`` returns a deterministic [0, 1] score that mirrors
  the heuristic evaluator's weighting — citation coverage, query
  coverage, confidence, and a length floor.
* ``select_best`` returns the top-scoring branch plus a ranked
  scoreboard for observability. Ties break on input order.
* The config gate ``reasoning_branch_count`` defaults to ``1``
  (behaviour-equivalent to pre-γ.2).

Pipeline fan-out wiring is deliberately out of scope here — the pure
primitives are the A+ ship, the LangGraph-shape change is the next
phase.
"""
from __future__ import annotations

import pytest

from aim.agents.branch_selector import (
    BranchCandidate,
    score_candidate,
    select_best,
)


def _cand(
    branch_id: str = "b1",
    *,
    answer_text: str = "a" * 200,
    cited_source_ids: tuple[str, ...] = ("s1", "s2"),
    total_sources: int = 2,
    covered_sub_queries: int = 1,
    total_sub_queries: int = 1,
    confidence: float = 0.8,
) -> BranchCandidate:
    return BranchCandidate(
        branch_id=branch_id,
        answer_text=answer_text,
        cited_source_ids=cited_source_ids,
        total_sources=total_sources,
        covered_sub_queries=covered_sub_queries,
        total_sub_queries=total_sub_queries,
        confidence=confidence,
    )


class TestScoreCandidate:
    def test_score_in_unit_interval(self):
        s = score_candidate(_cand())
        assert 0.0 <= s <= 1.0

    def test_perfect_candidate_scores_near_one(self):
        c = _cand(
            answer_text="a" * 500,
            cited_source_ids=("s1", "s2"),
            total_sources=2,
            covered_sub_queries=3,
            total_sub_queries=3,
            confidence=1.0,
        )
        assert score_candidate(c) == pytest.approx(1.0)

    def test_zero_sources_no_crash(self):
        c = _cand(
            cited_source_ids=(),
            total_sources=0,
            covered_sub_queries=0,
            total_sub_queries=0,
        )
        # No sources → citation_cov = 0; no sub-queries → query_cov = 1.
        s = score_candidate(c)
        assert 0.0 <= s <= 1.0

    def test_length_floor_penalises_short_answers(self):
        short = _cand(answer_text="tiny")
        long_ = _cand(answer_text="a" * 500)
        assert score_candidate(long_) > score_candidate(short)

    def test_higher_confidence_scores_higher(self):
        low = _cand(confidence=0.1)
        high = _cand(confidence=0.9)
        assert score_candidate(high) > score_candidate(low)

    def test_confidence_clamped(self):
        # Values outside [0,1] must not blow up the composite score.
        weird = _cand(confidence=1.5)
        assert 0.0 <= score_candidate(weird) <= 1.0
        negative = _cand(confidence=-0.3)
        assert 0.0 <= score_candidate(negative) <= 1.0

    def test_citation_coverage_counts_unique_ids(self):
        # Same source cited 3 times = 1 unique citation.
        repeated = _cand(
            cited_source_ids=("s1", "s1", "s1"),
            total_sources=3,
        )
        diverse = _cand(
            cited_source_ids=("s1", "s2", "s3"),
            total_sources=3,
        )
        assert score_candidate(diverse) > score_candidate(repeated)


class TestSelectBest:
    def test_picks_highest_scoring(self):
        weak = _cand("weak", confidence=0.1, answer_text="tiny")
        strong = _cand("strong", confidence=0.95, answer_text="a" * 500)
        winner, board = select_best([weak, strong])
        assert winner.branch_id == "strong"
        # Scoreboard is sorted descending.
        assert board[0][0] == "strong"
        assert board[1][0] == "weak"
        assert board[0][1] >= board[1][1]

    def test_tie_breaks_on_input_order(self):
        a = _cand("a")
        b = _cand("b")  # identical score
        winner, _ = select_best([a, b])
        assert winner.branch_id == "a"

    def test_single_candidate_is_winner(self):
        c = _cand("only")
        winner, board = select_best([c])
        assert winner.branch_id == "only"
        assert len(board) == 1

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            select_best([])


class TestBranchCountConfig:
    def test_default_fires_tree_of_thought(self):
        """Post-δ.3 A+: default flipped from 1 → 2 so tree-of-thought
        branching actually fires on every query instead of being dark.
        """
        from aim.config import Settings
        s = Settings(
            _env_file=None,
            anthropic_api_key="sk-test",
            openai_api_key="sk-test",
            neo4j_password="test",
            pinecone_api_key="test",
        )
        assert s.reasoning_branch_count == 2

    def test_accepts_higher_values(self):
        from aim.config import Settings
        s = Settings(
            _env_file=None,
            anthropic_api_key="sk-test",
            openai_api_key="sk-test",
            neo4j_password="test",
            pinecone_api_key="test",
            reasoning_branch_count=3,
        )
        assert s.reasoning_branch_count == 3

    def test_rejects_zero_and_over_cap(self):
        from aim.config import Settings
        with pytest.raises(Exception):  # pydantic ValidationError
            Settings(
                _env_file=None,
                anthropic_api_key="sk-test",
                openai_api_key="sk-test",
                neo4j_password="test",
                pinecone_api_key="test",
                reasoning_branch_count=0,
            )
        with pytest.raises(Exception):
            Settings(
                _env_file=None,
                anthropic_api_key="sk-test",
                openai_api_key="sk-test",
                neo4j_password="test",
                pinecone_api_key="test",
                reasoning_branch_count=99,
            )
