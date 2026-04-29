"""Anthropic Claude LLM provider."""
from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from aim.llm.base import LLMProvider, LLMResponse, LLMTokenChunk

log = structlog.get_logger(__name__)


def _to_langchain_messages(messages: list[dict[str, str]]) -> list:
    """Convert standard message dicts to LangChain message objects."""
    lc_messages = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
    return lc_messages


class AnthropicLLMProvider(LLMProvider):
    """Claude-backed LLM provider via LangChain.

    Reuses a single ChatAnthropic instance (and its HTTP connection pool)
    across all calls. Temperature and max_tokens are set per-call using
    ``bind()``, which returns a lightweight wrapper without creating a new
    HTTP client.
    """

    def __init__(self, *, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        # Single pooled client — avoids creating a new HTTP connection pool
        # per LLM call, which was a P1 performance bug.
        self._llm = ChatAnthropic(
            model=self._model,
            api_key=self._api_key,
            # Defaults — overridden per-call via .bind()
            temperature=0.1,
            max_tokens=4096,
        )

    def _configured(self, temperature: float, max_tokens: int) -> ChatAnthropic:
        """Return a bound copy with the given temperature/max_tokens.

        ``bind()`` creates a lightweight wrapper that inherits the underlying
        HTTP client (connection pool), so this is ~free.
        """
        return self._llm.bind(temperature=temperature, max_tokens=max_tokens)

    async def invoke(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        llm = self._configured(temperature, max_tokens)
        lc_messages = _to_langchain_messages(messages)
        response = await llm.ainvoke(lc_messages)

        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            input_tokens = response.usage_metadata.get("input_tokens", 0)
            output_tokens = response.usage_metadata.get("output_tokens", 0)

        return LLMResponse(
            content=str(response.content),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self._model,
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[LLMTokenChunk, None]:
        llm = ChatAnthropic(
            model=self._model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=self._api_key,
            stream_usage=True,
        )
        lc_messages = _to_langchain_messages(messages)

        input_tokens = 0
        output_tokens = 0

        async for chunk in llm.astream(lc_messages):
            content = chunk.content if isinstance(chunk.content, str) else ""
            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                input_tokens = chunk.usage_metadata.get("input_tokens", input_tokens)
                output_tokens = chunk.usage_metadata.get("output_tokens", output_tokens)
            if content:
                yield LLMTokenChunk(content=content)

        # Final chunk with usage metadata
        yield LLMTokenChunk(
            content="",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            is_final=True,
        )

    async def health_check(self) -> bool:
        try:
            response = await self._llm.ainvoke([HumanMessage(content="ping")])
            return bool(response.content)
        except Exception as exc:
            log.error("anthropic.health_check_failed", error=str(exc))
            return False
