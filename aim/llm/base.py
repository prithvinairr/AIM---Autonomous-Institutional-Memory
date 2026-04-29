"""Abstract interfaces for LLM and Embedding providers.

These protocols ensure data sovereignty by decoupling the AIM pipeline
from any specific vendor. Deploy with Anthropic, OpenAI, or a
fully-local stack (Ollama / vLLM / llama.cpp) — zero code changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMResponse:
    """Standardised LLM response regardless of provider."""
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


@dataclass(frozen=True)
class LLMTokenChunk:
    """Single token chunk during streaming."""
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    is_final: bool = False


class LLMProvider(ABC):
    """Provider-agnostic LLM interface.

    All AIM agent nodes (decomposer, synthesizer) call this interface
    instead of vendor-specific SDKs. Swap providers via config.
    """

    @abstractmethod
    async def invoke(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send messages and return a complete response."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[LLMTokenChunk, None]:
        """Stream token chunks. The last chunk has ``is_final=True``."""
        ...
        yield  # pragma: no cover — makes this a valid async generator

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider is reachable."""
        ...


class EmbeddingProvider(ABC):
    """Provider-agnostic embedding interface.

    Supports both cloud APIs (OpenAI) and local models (Ollama, sentence-transformers)
    via a uniform interface.
    """

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Embed a single text."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """Embed multiple texts. Returns (embeddings, tokens_used)."""
        ...

    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""
        ...
