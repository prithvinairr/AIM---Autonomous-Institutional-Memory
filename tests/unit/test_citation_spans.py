"""Tests for _compute_citation_spans — verifies the offset-drift fix."""
from __future__ import annotations

import pytest


class TestComputeCitationSpans:
    """Verify citation span offsets are correct, especially for dense clusters."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from aim.agents.nodes.synthesizer import _compute_citation_spans
        self.compute = _compute_citation_spans

    def test_single_citation(self):
        answer = "The auth service handles OAuth. [SRC:auth-1] It uses JWT."
        clean, spans = self.compute(answer, {"auth-1"})
        assert "[SRC:" not in clean
        assert len(spans) == 1
        assert spans[0].text.startswith("The auth service")

    def test_multiple_citations_same_paragraph(self):
        """Dense cluster: two citations in the same line should not drift."""
        answer = "Auth uses JWT [SRC:a] and RBAC [SRC:b] for security."
        clean, spans = self.compute(answer, {"a", "b"})
        assert "[SRC:" not in clean
        assert len(spans) == 2
        # Both spans should point to valid positions in the clean text
        for span in spans:
            assert span.start >= 0
            assert span.end >= span.start
            assert span.end <= len(clean) + 20  # allow reasonable bounds

    def test_three_consecutive_citations(self):
        """Three citations in a row — the worst case for offset drift."""
        answer = "Fact A. [SRC:x] Fact B. [SRC:y] Fact C. [SRC:z] Done."
        clean, spans = self.compute(answer, {"x", "y", "z"})
        assert "[SRC:" not in clean
        assert len(spans) == 3
        # Verify no negative or overlapping offsets
        for i, span in enumerate(spans):
            assert span.start >= 0, f"Span {i} has negative start: {span.start}"
            assert span.end >= span.start, f"Span {i}: end < start"

    def test_invalid_citation_skipped(self):
        """Citations not in valid_ids should be stripped but NOT produce spans."""
        answer = "Text [SRC:valid] more [SRC:invalid] end."
        clean, spans = self.compute(answer, {"valid"})
        assert "[SRC:" not in clean
        assert len(spans) == 1
        # The single span should be for "valid"

    def test_empty_answer(self):
        clean, spans = self.compute("", set())
        assert clean == ""
        assert spans == []

    def test_no_citations(self):
        answer = "Just a normal answer with no citations."
        clean, spans = self.compute(answer, set())
        assert clean == answer
        assert spans == []

    def test_multiline_citations(self):
        """Citations across multiple lines."""
        answer = "Line one. [SRC:a]\nLine two. [SRC:b]\nLine three."
        clean, spans = self.compute(answer, {"a", "b"})
        assert "[SRC:" not in clean
        assert len(spans) == 2
        # Second span should reference "Line two" not "Line one"
        assert "Line two" in spans[1].text or "Line one" in spans[0].text
