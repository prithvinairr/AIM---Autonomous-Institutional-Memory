"""Phase 5 — Circuit breaker wrapper around LLM providers.

Verifies that:
  * Repeated failures trip the per-provider breaker OPEN.
  * Once OPEN, further calls fail fast with ``CircuitOpenError`` — the
    wrapped delegate is never invoked.
  * Streaming honours the same breaker (first-chunk probe).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from aim.llm.base import LLMProvider, LLMResponse, LLMTokenChunk
from aim.llm.factory import CircuitBreakerLLMProvider
from aim.utils.circuit_breaker import CircuitOpenError, _registry


class _FlakyProvider(LLMProvider):
    """Always raises — used to trip the breaker."""

    def __init__(self) -> None:
        self.invoke_calls = 0
        self.stream_calls = 0

    async def invoke(self, messages, *, temperature=0.1, max_tokens=4096) -> LLMResponse:
        self.invoke_calls += 1
        raise RuntimeError("boom")

    async def stream(self, messages, *, temperature=0.1, max_tokens=4096) -> AsyncGenerator[LLMTokenChunk, None]:
        self.stream_calls += 1
        raise RuntimeError("boom")
        yield  # pragma: no cover

    async def health_check(self) -> bool:
        return False


class _HealthyProvider(LLMProvider):
    async def invoke(self, messages, *, temperature=0.1, max_tokens=4096) -> LLMResponse:
        return LLMResponse(content="ok", model="test")

    async def stream(self, messages, *, temperature=0.1, max_tokens=4096) -> AsyncGenerator[LLMTokenChunk, None]:
        yield LLMTokenChunk(content="ok", is_final=True)

    async def health_check(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _clear_breaker_registry():
    _registry.clear()
    yield
    _registry.clear()


@pytest.mark.asyncio
async def test_breaker_trips_open_after_repeated_failures(monkeypatch):
    """After threshold consecutive failures, subsequent calls fail fast."""
    from aim.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "circuit_breaker_threshold", 3, raising=False)

    flaky = _FlakyProvider()
    guarded = CircuitBreakerLLMProvider(flaky, breaker_name="llm_test")

    # First 3 calls propagate the RuntimeError and increment failure counter
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await guarded.invoke([])

    # Circuit is now OPEN — delegate must NOT be invoked again
    before = flaky.invoke_calls
    with pytest.raises(CircuitOpenError):
        await guarded.invoke([])
    assert flaky.invoke_calls == before, "delegate called despite OPEN breaker"


@pytest.mark.asyncio
async def test_healthy_provider_passes_through(monkeypatch):
    """A working delegate returns its response unchanged — breaker stays CLOSED."""
    from aim.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "circuit_breaker_threshold", 3, raising=False)

    guarded = CircuitBreakerLLMProvider(_HealthyProvider(), breaker_name="llm_healthy")
    resp = await guarded.invoke([])
    assert resp.content == "ok"


@pytest.mark.asyncio
async def test_stream_trips_breaker_on_repeated_failures(monkeypatch):
    """Streaming path also contributes to / respects the breaker."""
    from aim.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "circuit_breaker_threshold", 2, raising=False)

    flaky = _FlakyProvider()
    guarded = CircuitBreakerLLMProvider(flaky, breaker_name="llm_stream")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            async for _ in guarded.stream([]):
                pass

    with pytest.raises(CircuitOpenError):
        async for _ in guarded.stream([]):
            pass


@pytest.mark.asyncio
async def test_stream_yields_chunks_from_healthy_provider():
    guarded = CircuitBreakerLLMProvider(_HealthyProvider(), breaker_name="llm_stream_ok")
    chunks = [c async for c in guarded.stream([])]
    assert len(chunks) == 1
    assert chunks[0].content == "ok"
