"""Tests for SovereigntyGuardedLLMProvider reroute behavior."""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from aim.llm.base import LLMProvider, LLMResponse, LLMTokenChunk
from aim.llm.factory import SovereigntyGuardedLLMProvider


class _RecordingProvider(LLMProvider):
    def __init__(self, label: str) -> None:
        self.label = label
        self.invoke_calls: int = 0
        self.stream_calls: int = 0

    async def invoke(self, messages, *, temperature=0.1, max_tokens=4096) -> LLMResponse:
        self.invoke_calls += 1
        return LLMResponse(content=self.label, model=self.label)

    async def stream(self, messages, *, temperature=0.1, max_tokens=4096) -> AsyncGenerator[LLMTokenChunk, None]:
        self.stream_calls += 1
        yield LLMTokenChunk(content=self.label, is_final=True)

    async def health_check(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _reset_sovereignty():
    from aim.utils.sovereignty import reset_sovereignty_guard
    reset_sovereignty_guard()
    yield
    reset_sovereignty_guard()


def _configure_strict_with_local(monkeypatch, base_url: str = "http://localhost:11434/v1"):
    from aim.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "sovereignty_mode", "strict", raising=False)
    monkeypatch.setattr(s, "sovereignty_allowed_classifications", ["PUBLIC", "INTERNAL"], raising=False)
    monkeypatch.setattr(s, "external_llm_providers", ["anthropic", "openai"], raising=False)
    monkeypatch.setattr(s, "sovereignty_fallback_to_local", True, raising=False)
    monkeypatch.setattr(s, "llm_base_url", base_url, raising=False)
    monkeypatch.setattr(s, "openai_api_key", "test-key", raising=False)
    from aim.utils.sovereignty import reset_sovereignty_guard
    reset_sovereignty_guard()


@pytest.mark.asyncio
async def test_strict_mode_reroutes_to_local_when_restricted(monkeypatch):
    """RESTRICTED content with strict + fallback should not hit the external delegate."""
    _configure_strict_with_local(monkeypatch)

    external = _RecordingProvider("external")
    guarded = SovereigntyGuardedLLMProvider(external, provider_name="anthropic")
    local = _RecordingProvider("local")
    guarded._local = local  # inject local without spinning up real OpenAI provider

    messages = [{"role": "user", "content": "SSN: 123-45-6789"}]
    resp = await guarded.invoke(messages)

    assert resp.content == "local"
    assert local.invoke_calls == 1
    assert external.invoke_calls == 0


@pytest.mark.asyncio
async def test_clean_content_goes_to_external_delegate(monkeypatch):
    """Non-classified content continues to the external delegate unchanged."""
    _configure_strict_with_local(monkeypatch)

    external = _RecordingProvider("external")
    guarded = SovereigntyGuardedLLMProvider(external, provider_name="anthropic")
    local = _RecordingProvider("local")
    guarded._local = local

    messages = [{"role": "user", "content": "What services depend on Kafka?"}]
    resp = await guarded.invoke(messages)

    assert resp.content == "external"
    assert external.invoke_calls == 1
    assert local.invoke_calls == 0


@pytest.mark.asyncio
async def test_stream_reroutes_to_local(monkeypatch):
    """Streaming path also reroutes when flagged."""
    _configure_strict_with_local(monkeypatch)

    external = _RecordingProvider("external")
    guarded = SovereigntyGuardedLLMProvider(external, provider_name="anthropic")
    local = _RecordingProvider("local")
    guarded._local = local

    messages = [{"role": "user", "content": "SSN: 123-45-6789"}]
    chunks = [c async for c in guarded.stream(messages)]

    assert len(chunks) == 1
    assert chunks[0].content == "local"
    assert local.stream_calls == 1
    assert external.stream_calls == 0
