"""Unit tests for citation extraction and confidence scoring in synthesizer."""
from __future__ import annotations

import pytest

from aim.agents.nodes.synthesizer import (
    _compute_confidence,
    _extract_citation_map,
    _normalize_citation_tags,
)
from aim.schemas.provenance import SourceReference, SourceType


# ── Helpers ───────────────────────────────────────────────────────────────────

def _src(
    source_id: str,
    source_type: SourceType,
    confidence: float = 0.9,
) -> SourceReference:
    return SourceReference(
        source_id=source_id,
        source_type=source_type,
        content_snippet="test content",
        confidence=confidence,
    )


# ── _extract_citation_map ─────────────────────────────────────────────────────

def test_extracts_single_citation():
    answer = "The system uses Neo4j. [SRC:src-1]"
    result = _extract_citation_map(answer, {"src-1"})
    all_ids = {sid for ids in result.values() for sid in ids}
    assert "src-1" in all_ids


def test_extracts_multiple_citations_from_multiple_sentences():
    answer = "Graph is fast. [SRC:s1]\nVector search is accurate. [SRC:s2]"
    result = _extract_citation_map(answer, {"s1", "s2"})
    all_ids = {sid for ids in result.values() for sid in ids}
    assert "s1" in all_ids
    assert "s2" in all_ids


def test_extracts_multiple_sources_on_single_sentence():
    answer = "Combined insight. [SRC:s1][SRC:s2]"
    result = _extract_citation_map(answer, {"s1", "s2"})
    all_ids = {sid for ids in result.values() for sid in ids}
    assert "s1" in all_ids
    assert "s2" in all_ids


def test_filters_phantom_source_ids():
    answer = "Some fact. [SRC:real][SRC:invented]"
    result = _extract_citation_map(answer, {"real"})
    all_ids = {sid for ids in result.values() for sid in ids}
    assert "real" in all_ids
    assert "invented" not in all_ids


def test_ignores_sentences_with_no_valid_sources():
    answer = "Ungrounded claim. [SRC:fake]\nGrounded fact. [SRC:real]"
    result = _extract_citation_map(answer, {"real"})
    # Only the grounded sentence should appear
    assert len(result) == 1
    all_ids = {sid for ids in result.values() for sid in ids}
    assert "real" in all_ids


def test_deduplicates_identical_sentence_keys_with_counter():
    answer = "Same sentence here. [SRC:s1]\nSame sentence here. [SRC:s2]"
    result = _extract_citation_map(answer, {"s1", "s2"})
    # Two distinct keys must exist even though the sentence text is identical
    assert len(result) == 2


def test_empty_answer_returns_empty_dict():
    assert _extract_citation_map("", set()) == {}


def test_answer_with_no_src_tags_returns_empty_dict():
    result = _extract_citation_map("This answer has no citations at all.", {"s1"})
    assert result == {}


def test_question_mark_sentence_ending_is_extracted():
    answer = "Is this correct? [SRC:s1]"
    result = _extract_citation_map(answer, {"s1"})
    all_ids = {sid for ids in result.values() for sid in ids}
    assert "s1" in all_ids


def test_exclamation_mark_sentence_ending_is_extracted():
    answer = "It works! [SRC:s1]"
    result = _extract_citation_map(answer, {"s1"})
    all_ids = {sid for ids in result.values() for sid in ids}
    assert "s1" in all_ids


def test_normalizes_parenthesized_src_tags():
    answer = "The system uses Neo4j. (SRC:src-1)"
    normalized = _normalize_citation_tags(answer)
    assert normalized == "The system uses Neo4j. [SRC:src-1]"
    result = _extract_citation_map(normalized, {"src-1"})
    all_ids = {sid for ids in result.values() for sid in ids}
    assert "src-1" in all_ids


# ── _compute_confidence ───────────────────────────────────────────────────────

def test_confidence_returns_zero_with_no_sources():
    assert _compute_confidence({}, {}) == 0.0


def test_confidence_neo4j_cited_is_high():
    sources = {"n1": _src("n1", SourceType.NEO4J_GRAPH, 0.95)}
    citation_map = {"Graph stores entities.": ["n1"]}
    score = _compute_confidence(sources, citation_map)
    # type_weight=1.0, usage_weight=1.0, confidence=0.95 → 0.95
    assert 0.9 <= score <= 1.0


def test_confidence_uncited_source_reduces_score():
    """When a high-quality source is uncited, the overall score drops compared
    to citing it — because uncited sources get only 0.2× usage weight,
    effectively wasting their retrieval signal in the weighted average.
    """
    sources = {
        "n1": _src("n1", SourceType.NEO4J_GRAPH, 0.7),
        "n2": _src("n2", SourceType.NEO4J_GRAPH, 0.95),
    }
    score_all_cited = _compute_confidence(
        sources, {"Fact A.": ["n1"], "Fact B.": ["n2"]}
    )
    # Only cite n1 (lower quality), leave n2 (higher quality) uncited
    score_one_cited = _compute_confidence(sources, {"Fact A.": ["n1"]})
    # Citing both gives a higher weighted average than leaving the better source uncited
    assert score_all_cited > score_one_cited


def test_confidence_slack_lower_than_neo4j_at_equal_raw_confidence():
    """Type weights differentiate source types when mixed together.

    With a single source, the weighted mean always equals ref.confidence
    (the type weight cancels out in numerator/denominator). To see the
    type reliability effect, we mix each with a neutral baseline source.
    """
    baseline = _src("base", SourceType.LLM_SYNTHESIS, 0.5)
    neo4j_mix = {
        "n1": _src("n1", SourceType.NEO4J_GRAPH, 0.9),
        "base": baseline,
    }
    slack_mix = {
        "s1": _src("s1", SourceType.SLACK_MCP, 0.9),
        "base": baseline,
    }
    score_neo4j = _compute_confidence(neo4j_mix, {"Fact.": ["n1"], "Base.": ["base"]})
    score_slack = _compute_confidence(slack_mix, {"Fact.": ["s1"], "Base.": ["base"]})
    assert score_neo4j > score_slack


def test_confidence_source_type_ordering():
    """NEO4J > JIRA > PINECONE > SLACK > LLM — verified by mixing each type
    with a fixed neutral baseline to reveal the type weight difference.
    """
    types = [
        SourceType.NEO4J_GRAPH,
        SourceType.JIRA_MCP,
        SourceType.PINECONE_VECTOR,
        SourceType.SLACK_MCP,
        SourceType.LLM_SYNTHESIS,
    ]
    baseline = _src("base", SourceType.PINECONE_VECTOR, 0.5)
    scores = []
    for i, t in enumerate(types):
        sid = f"src-{i}"
        sources = {sid: _src(sid, t, 1.0), "base": baseline}
        citation_map = {f"Sentence {i}.": [sid], "Baseline.": ["base"]}
        scores.append(_compute_confidence(sources, citation_map))
    assert scores == sorted(scores, reverse=True)


def test_confidence_is_bounded_between_0_and_1():
    sources = {
        f"s{i}": _src(f"s{i}", SourceType.PINECONE_VECTOR, 0.75)
        for i in range(5)
    }
    citation_map = {f"Sentence {i}.": [f"s{i}"] for i in range(5)}
    score = _compute_confidence(sources, citation_map)
    assert 0.0 <= score <= 1.0


def test_confidence_with_mixed_source_types_is_weighted_average():
    sources = {
        "neo4j-1": _src("neo4j-1", SourceType.NEO4J_GRAPH, 0.9),
        "slack-1": _src("slack-1", SourceType.SLACK_MCP, 0.9),
        "vec-1": _src("vec-1", SourceType.PINECONE_VECTOR, 0.9),
    }
    citation_map = {
        "Graph fact.": ["neo4j-1"],
        "Slack message.": ["slack-1"],
        "Vector snippet.": ["vec-1"],
    }
    score = _compute_confidence(sources, citation_map)
    # Weights: NEO4J=1.0, PINECONE=0.85, SLACK=0.7; all conf=0.9
    # weighted_sum = 0.9*(1.0 + 0.85 + 0.7) = 0.9*2.55 = 2.295
    # total_weight = 2.55
    # score = 2.295/2.55 = 0.9 (conf is same for all, so overall = conf)
    assert abs(score - 0.9) < 0.001


def test_confidence_result_is_rounded_to_4_decimal_places():
    sources = {"s1": _src("s1", SourceType.PINECONE_VECTOR, 1 / 3)}
    score = _compute_confidence(sources, {"Fact.": ["s1"]})
    assert score == round(score, 4)
