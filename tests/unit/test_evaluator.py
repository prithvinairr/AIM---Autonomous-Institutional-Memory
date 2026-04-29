"""Tests for the evaluator node — heuristic answer scoring and reloop decisions."""
from __future__ import annotations

import pytest

from aim.agents.nodes.evaluator import (
    _MAX_LOOPS,
    _RELOOP_THRESHOLD,
    _STRUCTURED_GAP_PREFIX,
    _score_answer_length,
    _score_citation_coverage,
    _score_query_coverage,
    evaluate_answer,
)
from aim.agents.state import AgentState
from uuid import uuid4

from aim.schemas.provenance import ProvenanceMap, SourceReference, SourceType


def _make_state(**overrides) -> AgentState:
    defaults = dict(
        query_id=uuid4(),
        original_query="test query",
        sub_queries=["sq1", "sq2"],
        sources={
            "src-1": SourceReference(source_type=SourceType.NEO4J_GRAPH, confidence=0.9, content_snippet="graph entity data"),
            "src-2": SourceReference(source_type=SourceType.PINECONE_VECTOR, confidence=0.8, content_snippet="vector snippet"),
        },
        citation_map={"claim-1": ["src-1"]},
        sub_query_source_map={"sq1": ["src-1"], "sq2": ["src-2"]},
        answer="A decent answer that is long enough for the evaluator.",
        provenance=ProvenanceMap(query_id=uuid4(), overall_confidence=0.85),
        loop_count=0,
        reasoning_steps=[],
    )
    defaults.update(overrides)
    return AgentState(**defaults)


# ── Citation coverage ────────────────────────────────────────────────────────


class TestCitationCoverage:
    def test_no_sources_returns_zero(self):
        state = _make_state(sources={})
        assert _score_citation_coverage(state) == 0.0

    def test_half_sources_cited(self):
        state = _make_state()  # 2 sources, 1 cited
        score = _score_citation_coverage(state)
        assert score == pytest.approx(0.5)

    def test_all_sources_cited(self):
        state = _make_state(
            citation_map={"a": ["src-1"], "b": ["src-2"]},
        )
        score = _score_citation_coverage(state)
        assert score == pytest.approx(1.0)

    def test_capped_at_one(self):
        # Even if citation_map references unknown IDs, ratio is capped at 1
        state = _make_state(
            citation_map={"a": ["src-1", "src-2", "src-extra"]},
        )
        score = _score_citation_coverage(state)
        assert score <= 1.0


# ── Query coverage ───────────────────────────────────────────────────────────


class TestQueryCoverage:
    def test_no_sub_queries_returns_one(self):
        state = _make_state(sub_queries=[])
        assert _score_query_coverage(state) == 1.0

    def test_all_covered(self):
        state = _make_state()
        assert _score_query_coverage(state) == 1.0

    def test_partial_coverage(self):
        state = _make_state(
            sub_query_source_map={"sq1": ["src-1"], "sq2": []},
        )
        assert _score_query_coverage(state) == pytest.approx(0.5)

    def test_none_covered(self):
        state = _make_state(sub_query_source_map={})
        assert _score_query_coverage(state) == 0.0


# ── Answer length scoring ────────────────────────────────────────────────────


class TestAnswerLength:
    def test_long_answer(self):
        state = _make_state(answer="x" * 250)
        assert _score_answer_length(state) == 1.0

    def test_medium_answer(self):
        state = _make_state(answer="x" * 120)
        assert _score_answer_length(state) == 0.6

    def test_short_answer(self):
        state = _make_state(answer="x" * 60)
        assert _score_answer_length(state) == 0.3

    def test_very_short_answer(self):
        state = _make_state(answer="x" * 10)
        assert _score_answer_length(state) == 0.1


# ── Full evaluate_answer ─────────────────────────────────────────────────────


class TestEvaluateAnswer:
    @pytest.mark.asyncio
    async def test_good_answer_no_reloop(self):
        state = _make_state(
            citation_map={"a": ["src-1"], "b": ["src-2"]},
            answer="x" * 300,
        )
        result = await evaluate_answer(state)
        assert result.evaluation_score > _RELOOP_THRESHOLD
        assert result.needs_reloop is False
        assert result.loop_count == 0
        assert "sufficient" in result.reasoning_steps[-1]

    @pytest.mark.asyncio
    async def test_poor_answer_triggers_reloop(self):
        state = _make_state(
            sources={"s1": SourceReference(source_type=SourceType.NEO4J_GRAPH, confidence=0.2, content_snippet="low confidence data")},
            citation_map={},
            sub_query_source_map={},
            answer="short",
            provenance=ProvenanceMap(query_id=uuid4(), overall_confidence=0.1),
        )
        result = await evaluate_answer(state)
        assert result.evaluation_score < _RELOOP_THRESHOLD
        assert result.needs_reloop is True
        assert result.loop_count == 1
        assert result.evaluation_feedback  # non-empty feedback
        assert "re-searching" in result.reasoning_steps[-1]

    @pytest.mark.asyncio
    async def test_no_reloop_when_max_loops_reached(self):
        state = _make_state(
            sources={"s1": SourceReference(source_type=SourceType.NEO4J_GRAPH, confidence=0.1, content_snippet="minimal data")},
            citation_map={},
            sub_query_source_map={},
            answer="short",
            provenance=ProvenanceMap(query_id=uuid4(), overall_confidence=0.1),
            loop_count=_MAX_LOOPS,  # already exhausted
        )
        result = await evaluate_answer(state)
        assert result.needs_reloop is False

    @pytest.mark.asyncio
    async def test_feedback_mentions_gaps(self):
        state = _make_state(
            sources={"s1": SourceReference(source_type=SourceType.NEO4J_GRAPH, confidence=0.2, content_snippet="low confidence data")},
            citation_map={},
            sub_query_source_map={"sq1": [], "sq2": []},
            answer="tiny",
            provenance=ProvenanceMap(query_id=uuid4(), overall_confidence=0.1),
        )
        result = await evaluate_answer(state)
        # Feedback should mention low citation, uncovered sub-queries, low confidence, short answer
        assert "sources" in result.evaluation_feedback.lower() or "cited" in result.evaluation_feedback.lower()

    @pytest.mark.asyncio
    async def test_missing_hops_emit_structured_feedback_and_cap_multihop_loops(self):
        state = _make_state(
            is_multi_hop=True,
            missing_hops=["Auth Service ↔ ADR-003"],
            loop_count=0,
            citation_map={},
            answer="short",
            provenance=ProvenanceMap(query_id=uuid4(), overall_confidence=0.1),
        )

        result = await evaluate_answer(state)

        assert result.needs_reloop is True
        assert _STRUCTURED_GAP_PREFIX in result.evaluation_feedback
        assert '"source":"Auth Service"' in result.evaluation_feedback
        assert '"target":"ADR-003"' in result.evaluation_feedback

        capped_state = state.model_copy(update={"loop_count": 2})
        capped_result = await evaluate_answer(capped_state)

        assert capped_result.needs_reloop is False
