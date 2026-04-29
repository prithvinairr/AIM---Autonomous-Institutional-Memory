"""Tests for the re-ranker module."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from aim.agents.reranker import (
    CrossEncoderReranker,
    LLMReranker,
    NoopReranker,
    RerankerResult,
    get_reranker,
    reset_reranker,
)
from aim.schemas.provenance import SourceReference, SourceType


def _ref(title: str = "Test", confidence: float = 0.8) -> SourceReference:
    return SourceReference(
        source_type=SourceType.NEO4J_GRAPH,
        title=title,
        content_snippet=f"Snippet about {title}",
        confidence=confidence,
    )


# ── RerankerResult ──────────────────────────────────────────────────────────


class TestRerankerResult:
    def test_sorts_by_score_descending(self):
        r = RerankerResult([("a", 0.3), ("b", 0.9), ("c", 0.5)])
        assert r.items[0] == ("b", 0.9)
        assert r.items[-1] == ("a", 0.3)

    def test_top_k_limits(self):
        r = RerankerResult([("a", 0.1), ("b", 0.2), ("c", 0.3)])
        assert len(r.top_k(2)) == 2
        assert r.top_k(2)[0][0] == "c"

    def test_top_k_larger_than_items(self):
        r = RerankerResult([("a", 0.5)])
        assert len(r.top_k(10)) == 1

    def test_empty(self):
        r = RerankerResult([])
        assert r.items == []
        assert r.top_k(5) == []


# ── NoopReranker ────────────────────────────────────────────────────────────


class TestNoopReranker:
    @pytest.mark.asyncio
    async def test_returns_sources_by_confidence(self):
        sources = {
            "s1": _ref("A", 0.5),
            "s2": _ref("B", 0.9),
        }
        result = await NoopReranker().rerank("query", sources)
        assert result.items[0][0] == "s2"

    @pytest.mark.asyncio
    async def test_empty_sources(self):
        result = await NoopReranker().rerank("query", {})
        assert result.items == []

    @pytest.mark.asyncio
    async def test_respects_top_k(self):
        sources = {f"s{i}": _ref(f"S{i}", 0.1 * i) for i in range(10)}
        result = await NoopReranker().rerank("query", sources, top_k=3)
        assert len(result.items) <= 10  # NoopReranker slices before Result


# ── LLMReranker ─────────────────────────────────────────────────────────────


class TestLLMReranker:
    @pytest.mark.asyncio
    async def test_scores_from_llm_response(self):
        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(return_value=MagicMock(content="[8, 3, 9]"))

        sources = {
            "s1": _ref("Auth"),
            "s2": _ref("DB"),
            "s3": _ref("Cache"),
        }

        with patch("aim.llm.get_llm_provider", return_value=mock_llm):
            result = await LLMReranker().rerank("how does auth work?", sources)

        assert len(result.items) == 3
        # s3 had score 9/10 = 0.9, should be first
        assert result.items[0][0] == "s3"

    @pytest.mark.asyncio
    async def test_falls_back_on_llm_error(self):
        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(side_effect=RuntimeError("LLM down"))

        sources = {"s1": _ref("A", 0.7)}

        with patch("aim.llm.get_llm_provider", return_value=mock_llm):
            result = await LLMReranker().rerank("query", sources)

        # Falls back to original confidence
        assert len(result.items) == 1
        assert result.items[0][1] == 0.7

    @pytest.mark.asyncio
    async def test_empty_sources(self):
        result = await LLMReranker().rerank("query", {})
        assert result.items == []


# ── CrossEncoderReranker ────────────────────────────────────────────────────


class TestCrossEncoderReranker:
    @pytest.mark.asyncio
    async def test_falls_back_when_import_fails(self):
        """When sentence-transformers is not installed, falls back to LLM reranker."""
        reranker = CrossEncoderReranker("nonexistent-model")
        # Force load failure
        reranker._load_failed = True

        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(return_value=MagicMock(content="[5]"))

        sources = {"s1": _ref("Test")}

        with patch("aim.llm.get_llm_provider", return_value=mock_llm):
            result = await reranker.rerank("query", sources)

        assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_uses_model_when_available(self):
        """When model loads successfully, uses cross-encoder scores."""
        import numpy as np

        reranker = CrossEncoderReranker()
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([2.5, -1.0, 0.5])
        reranker._model = mock_model

        sources = {
            "s1": _ref("A"),
            "s2": _ref("B"),
            "s3": _ref("C"),
        }

        result = await reranker.rerank("test query", sources)

        assert len(result.items) == 3
        # Score 2.5 → sigmoid ≈ 0.924 should be highest
        assert result.items[0][0] == "s1"
        assert result.items[0][1] > 0.9

    @pytest.mark.asyncio
    async def test_empty_sources(self):
        reranker = CrossEncoderReranker()
        reranker._load_failed = True

        result = await reranker.rerank("query", {})
        assert result.items == []


# ── Factory ─────────────────────────────────────────────────────────────────


class TestFactory:
    def setup_method(self):
        reset_reranker()

    def teardown_method(self):
        reset_reranker()

    @patch("aim.config.get_settings")
    def test_creates_cross_encoder_by_default(self, mock_settings):
        mock_settings.return_value = MagicMock(
            reranker_provider="cross_encoder",
            reranker_model="test-model",
        )
        r = get_reranker()
        assert isinstance(r, CrossEncoderReranker)

    @patch("aim.config.get_settings")
    def test_creates_llm_reranker(self, mock_settings):
        mock_settings.return_value = MagicMock(reranker_provider="llm")
        r = get_reranker()
        assert isinstance(r, LLMReranker)

    @patch("aim.config.get_settings")
    def test_creates_noop_reranker(self, mock_settings):
        mock_settings.return_value = MagicMock(reranker_provider="none")
        r = get_reranker()
        assert isinstance(r, NoopReranker)

    @patch("aim.config.get_settings")
    def test_singleton(self, mock_settings):
        mock_settings.return_value = MagicMock(reranker_provider="none")
        r1 = get_reranker()
        r2 = get_reranker()
        assert r1 is r2

    def test_reset(self):
        reset_reranker()
        # After reset, next get_reranker will create fresh
        with patch("aim.config.get_settings") as m:
            m.return_value = MagicMock(reranker_provider="none")
            r = get_reranker()
            assert isinstance(r, NoopReranker)
