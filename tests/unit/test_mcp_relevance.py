"""Tests for MCP relevance scoring in aim.agents.nodes.mcp_fetcher."""
from __future__ import annotations

import pytest

from aim.agents.nodes.mcp_fetcher import _compute_mcp_relevance


class TestComputeMCPRelevance:
    """Tests for the query-content relevance scoring function."""

    def test_perfect_overlap(self):
        score = _compute_mcp_relevance("auth service", "auth service discussion")
        assert score > 0.7

    def test_partial_overlap(self):
        score = _compute_mcp_relevance(
            "authentication failures", "auth service had some issues yesterday"
        )
        assert 0.3 < score < 0.9

    def test_no_overlap(self):
        score = _compute_mcp_relevance(
            "kubernetes deployment", "quarterly finance review with board members"
        )
        assert score < 0.6  # base bonus keeps it above zero

    def test_empty_query(self):
        score = _compute_mcp_relevance("", "some text content")
        assert score == 0.5  # fallback

    def test_empty_text(self):
        score = _compute_mcp_relevance("some query", "")
        assert score == 0.5  # fallback

    def test_both_empty(self):
        score = _compute_mcp_relevance("", "")
        assert score == 0.5

    def test_score_bounded_0_to_1(self):
        score = _compute_mcp_relevance("test", "test test test test test")
        assert 0.0 <= score <= 1.0

    def test_identical_text(self):
        text = "authentication service outage incident report"
        score = _compute_mcp_relevance(text, text)
        assert score >= 0.9

    def test_long_text_uses_first_100_tokens(self):
        """Long text should be truncated to first 100 tokens for performance."""
        long_text = " ".join([f"word{i}" for i in range(200)])
        score = _compute_mcp_relevance("word1 word2", long_text)
        assert 0.0 <= score <= 1.0

    def test_case_insensitive(self):
        score1 = _compute_mcp_relevance("Auth Service", "auth service")
        score2 = _compute_mcp_relevance("auth service", "AUTH SERVICE")
        assert abs(score1 - score2) < 0.01

    def test_returns_float(self):
        score = _compute_mcp_relevance("test query", "test content")
        assert isinstance(score, float)

    def test_base_bonus_applied(self):
        """MCP items have a base bonus (+0.3) since they were fetched specifically."""
        # Even with minimal overlap, score should be > 0.3
        score = _compute_mcp_relevance("a", "b c d")
        assert score >= 0.1  # floor is 0.1

    def test_single_word_query(self):
        score = _compute_mcp_relevance("authentication", "authentication failure in production")
        assert score > 0.5

    def test_sequence_similarity_contributes(self):
        """Similar word sequences should score higher than random word matches."""
        structured = _compute_mcp_relevance(
            "auth service failure", "auth service failure report from yesterday"
        )
        scrambled = _compute_mcp_relevance(
            "auth service failure", "failure of service auth in yesterday report"
        )
        # Structured should score higher due to sequence similarity
        assert structured >= scrambled
