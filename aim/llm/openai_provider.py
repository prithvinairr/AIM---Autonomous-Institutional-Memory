"""OpenAI-compatible LLM and Embedding providers.

Works with:
  - OpenAI API (default)
  - Ollama (set LLM_BASE_URL=http://localhost:11434/v1)
  - vLLM (set LLM_BASE_URL=http://localhost:8000/v1)
  - llama.cpp server (set LLM_BASE_URL=http://localhost:8080/v1)
  - Any OpenAI-compatible endpoint (LocalAI, LiteLLM, etc.)
"""
from __future__ import annotations

import hashlib
from collections.abc import AsyncGenerator

import structlog
from openai import AsyncOpenAI

from aim.llm.base import EmbeddingProvider, LLMProvider, LLMResponse, LLMTokenChunk

log = structlog.get_logger(__name__)


class OpenAILLMProvider(LLMProvider):
    """OpenAI-compatible LLM provider.

    Pass a custom ``base_url`` to point at a local inference server.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> None:
        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    async def invoke(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        usage = response.usage
        return LLMResponse(
            content=content,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=self._model,
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[LLMTokenChunk, None]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )

        input_tokens = 0
        output_tokens = 0

        async for chunk in stream:
            if chunk.usage:
                input_tokens = chunk.usage.prompt_tokens or 0
                output_tokens = chunk.usage.completion_tokens or 0
            if chunk.choices and chunk.choices[0].delta.content:
                yield LLMTokenChunk(content=chunk.choices[0].delta.content)

        yield LLMTokenChunk(
            content="",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            is_final=True,
        )

    async def health_check(self) -> bool:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            return bool(response.choices)
        except Exception as exc:
            log.error("openai_llm.health_check_failed", error=str(exc))
            return False


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI-compatible embedding provider.

    Pass a custom ``base_url`` for local embedding servers (Ollama, TEI, etc.).
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        dim: int = 1536,
        base_url: str | None = None,
    ) -> None:
        self._model = model
        self._dim = dim
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=text[:32768],
            encoding_format="float",
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> tuple[list[list[float]], int]:
        if not texts:
            return [], 0
        truncated = [t[:32768] for t in texts]
        response = await self._client.embeddings.create(
            model=self._model,
            input=truncated,
            encoding_format="float",
        )
        embeddings = [d.embedding for d in response.data]
        tokens = response.usage.total_tokens if response.usage else 0
        return embeddings, tokens

    def dimension(self) -> int:
        return self._dim
