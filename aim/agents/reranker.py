"""Re-ranking providers for cross-modal source fusion.

Three strategies:
  - **CrossEncoderReranker** — learned relevance via ``sentence-transformers``
    cross-encoder (fast, ~6ms per pair on CPU). Falls back to ``LLMReranker``
    if the model cannot be loaded.
  - **LLMReranker** — uses the existing LLM provider to score relevance
    (more expensive, higher quality on complex queries).
  - **NoopReranker** — returns sources in their original order (title-based
    fusion from the synthesizer still applies).

Factory singleton mirrors ``aim/llm/factory.py``.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from aim.schemas.provenance import SourceReference

log = structlog.get_logger(__name__)


class RerankerResult:
    """Ranked list of (source_id, relevance_score) pairs, highest first."""

    __slots__ = ("items",)

    def __init__(self, items: list[tuple[str, float]]) -> None:
        self.items = sorted(items, key=lambda x: x[1], reverse=True)

    def top_k(self, k: int) -> list[tuple[str, float]]:
        return self.items[:k]


class RerankerProvider(ABC):
    """Abstract re-ranker interface."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        sources: dict[str, "SourceReference"],
        *,
        top_k: int = 15,
    ) -> RerankerResult:
        """Score each source against the query and return ranked results."""
        ...


class CrossEncoderReranker(RerankerProvider):
    """Learned cross-encoder re-ranker using sentence-transformers.

    Loads the model lazily on first call. If the package or model is
    unavailable, falls back to ``LLMReranker`` automatically.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self._model_name = model_name
        self._model = None
        self._load_failed = False

    def _ensure_model(self):
        if self._model is not None or self._load_failed:
            return
        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self._model_name)
            log.info("reranker.cross_encoder.loaded", model=self._model_name)
        except Exception as exc:
            log.warning("reranker.cross_encoder.load_failed", error=str(exc))
            self._load_failed = True

    async def rerank(
        self,
        query: str,
        sources: dict[str, "SourceReference"],
        *,
        top_k: int = 15,
    ) -> RerankerResult:
        self._ensure_model()

        if self._load_failed or self._model is None:
            # Fallback to LLM reranker
            fallback = LLMReranker()
            return await fallback.rerank(query, sources, top_k=top_k)

        pairs: list[tuple[str, str]] = []
        src_ids: list[str] = []
        for src_id, ref in sources.items():
            text = ref.content_snippet or ref.title or ""
            if text:
                pairs.append((query, text[:512]))
                src_ids.append(src_id)

        if not pairs:
            return RerankerResult([])

        # Run CPU-bound cross-encoder in thread pool
        model = self._model
        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(
            None,
            lambda: model.predict([(q, d) for q, d in pairs]).tolist(),
        )

        # Normalize scores to [0, 1] via sigmoid
        import math
        items = []
        for sid, raw_score in zip(src_ids, scores):
            normalized = 1 / (1 + math.exp(-raw_score))
            items.append((sid, round(normalized, 4)))

        result = RerankerResult(items)
        return RerankerResult(result.top_k(top_k))


class LLMReranker(RerankerProvider):
    """Re-ranker using the existing LLM provider for relevance scoring.

    Sends a batch prompt asking the LLM to score each source 0-10 for
    relevance. More expensive but high quality.
    """

    async def rerank(
        self,
        query: str,
        sources: dict[str, "SourceReference"],
        *,
        top_k: int = 15,
    ) -> RerankerResult:
        from aim.llm import get_llm_provider

        if not sources:
            return RerankerResult([])

        # Build scoring prompt
        source_list = []
        src_ids = []
        for i, (src_id, ref) in enumerate(sources.items()):
            text = (ref.content_snippet or ref.title or "")[:300]
            source_list.append(f"[{i}] {text}")
            src_ids.append(src_id)

        prompt = (
            f"Rate each source's relevance to the query on a scale of 0-10.\n"
            f"Query: {query}\n\nSources:\n" + "\n".join(source_list) +
            f"\n\nReturn ONLY a JSON array of scores, e.g. [8, 3, 7, ...]"
        )

        try:
            llm = get_llm_provider()
            response = await llm.invoke(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=256,
            )

            import json
            import re
            # Extract JSON array from response
            match = re.search(r"\[[\d\s,\.]+\]", response.content)
            if match:
                raw_scores = json.loads(match.group())
                items = []
                for sid, score in zip(src_ids, raw_scores):
                    normalized = min(max(float(score) / 10.0, 0.0), 1.0)
                    items.append((sid, round(normalized, 4)))
                return RerankerResult(items[:top_k])
        except Exception as exc:
            log.warning("reranker.llm.error", error=str(exc))

        # Fallback: return sources with their original confidence
        items = [
            (sid, ref.confidence)
            for sid, ref in sources.items()
        ]
        return RerankerResult(items[:top_k])


class NoopReranker(RerankerProvider):
    """Pass-through — returns sources in original confidence order."""

    async def rerank(
        self,
        query: str,
        sources: dict[str, "SourceReference"],
        *,
        top_k: int = 15,
    ) -> RerankerResult:
        items = [
            (sid, ref.confidence)
            for sid, ref in sources.items()
        ]
        return RerankerResult(items[:top_k])


# ── Factory ──────────────────────────────────────────────────────────────────

_reranker: RerankerProvider | None = None


def get_reranker() -> RerankerProvider:
    """Singleton factory — reads ``reranker_provider`` from settings."""
    global _reranker
    if _reranker is not None:
        return _reranker

    from aim.config import get_settings
    settings = get_settings()

    if settings.reranker_provider == "cross_encoder":
        _reranker = CrossEncoderReranker(settings.reranker_model)
    elif settings.reranker_provider == "llm":
        _reranker = LLMReranker()
    else:
        _reranker = NoopReranker()

    log.info("reranker.init", provider=settings.reranker_provider)
    return _reranker


def reset_reranker() -> None:
    """Reset singleton — for testing."""
    global _reranker
    _reranker = None
