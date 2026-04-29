"""Phase δ.2 — embedding sovereignty guard symmetry.

Panel audit flagged that only completion calls ran through the sovereignty
guard. Embedding calls — which dispatch the same raw document text to the
same external providers — bypassed the check entirely. A document
classified RESTRICTED could leak to OpenAI embeddings with zero gate.

This suite pins the fix: :class:`SovereigntyGuardedEmbeddingProvider`
runs the guard on every ``embed`` / ``embed_batch`` call, reroutes to a
local embedder in strict-mode + fallback-enabled config, and propagates
raw violations when fallback is off.
"""
from __future__ import annotations

import pytest

from aim.llm.base import EmbeddingProvider
from aim.llm.factory import SovereigntyGuardedEmbeddingProvider


class _FakeEmbedder(EmbeddingProvider):
    """Records calls so tests can assert which delegate fired."""

    def __init__(self, tag: str, dim: int = 8) -> None:
        self.tag = tag
        self._dim = dim
        self.embed_calls: list[str] = []
        self.embed_batch_calls: list[list[str]] = []

    async def embed(self, text: str) -> list[float]:
        self.embed_calls.append(text)
        return [0.0] * self._dim

    async def embed_batch(self, texts: list[str]):
        self.embed_batch_calls.append(list(texts))
        return [[0.0] * self._dim for _ in texts], len(texts)

    def dimension(self) -> int:
        return self._dim


@pytest.fixture(autouse=True)
def _reset_guard():
    """The guard is a module-level singleton; reset between tests so each
    test's settings monkeypatches take effect."""
    from aim.utils.sovereignty import reset_sovereignty_guard

    reset_sovereignty_guard()
    yield
    reset_sovereignty_guard()


class TestEmbeddingGuardRoutes:
    @pytest.mark.asyncio
    async def test_public_text_goes_to_external_delegate(self, monkeypatch):
        """Unclassified text — route to the external embedder as normal."""
        from aim.config import get_settings

        s = get_settings()
        monkeypatch.setattr(s, "sovereignty_mode", "strict")
        monkeypatch.setattr(s, "sovereignty_allowed_classifications", ["PUBLIC", "INTERNAL"])
        monkeypatch.setattr(s, "external_llm_providers", ["openai", "anthropic"])
        monkeypatch.setattr(s, "sovereignty_fallback_to_local", True)
        monkeypatch.setattr(s, "embedding_base_url", "http://localhost:11434/v1")

        external = _FakeEmbedder("openai")
        guarded = SovereigntyGuardedEmbeddingProvider(external, provider_name="openai")

        vec = await guarded.embed("What services depend on Kafka?")
        assert vec == [0.0] * 8
        assert external.embed_calls == ["What services depend on Kafka?"]

    @pytest.mark.asyncio
    async def test_restricted_text_reroutes_to_local(self, monkeypatch):
        """RESTRICTED text must never hit the external embedder."""
        from aim.config import get_settings

        s = get_settings()
        monkeypatch.setattr(s, "sovereignty_mode", "strict")
        monkeypatch.setattr(s, "sovereignty_allowed_classifications", ["PUBLIC", "INTERNAL"])
        monkeypatch.setattr(s, "external_llm_providers", ["openai", "anthropic"])
        monkeypatch.setattr(s, "sovereignty_fallback_to_local", True)
        monkeypatch.setattr(s, "embedding_base_url", "http://localhost:11434/v1")
        monkeypatch.setattr(s, "llm_base_url", "http://localhost:11434/v1")

        external = _FakeEmbedder("openai")
        guarded = SovereigntyGuardedEmbeddingProvider(external, provider_name="openai")

        # Don't actually hit Ollama — patch the lazy local builder to
        # return a recorder so we can assert which embedder fired.
        local = _FakeEmbedder("local")
        guarded._local = local  # inject the lazy singleton directly

        await guarded.embed("SSN: 123-45-6789")

        assert external.embed_calls == [], "classified text must not reach external embedder"
        assert local.embed_calls == ["SSN: 123-45-6789"]

    @pytest.mark.asyncio
    async def test_batch_reroute_is_all_or_nothing(self, monkeypatch):
        """If any text in a batch triggers a reroute, the whole batch is
        rerouted — see class docstring for the dimension-safety rationale."""
        from aim.config import get_settings

        s = get_settings()
        monkeypatch.setattr(s, "sovereignty_mode", "strict")
        monkeypatch.setattr(s, "sovereignty_allowed_classifications", ["PUBLIC", "INTERNAL"])
        monkeypatch.setattr(s, "external_llm_providers", ["openai"])
        monkeypatch.setattr(s, "sovereignty_fallback_to_local", True)
        monkeypatch.setattr(s, "embedding_base_url", "http://localhost:11434/v1")

        external = _FakeEmbedder("openai")
        guarded = SovereigntyGuardedEmbeddingProvider(external, provider_name="openai")
        local = _FakeEmbedder("local")
        guarded._local = local

        texts = ["weather today", "SSN: 123-45-6789", "kafka dependencies"]
        vecs, tokens = await guarded.embed_batch(texts)

        assert external.embed_batch_calls == []
        assert local.embed_batch_calls == [texts]
        assert len(vecs) == 3
        assert tokens == 3

    @pytest.mark.asyncio
    async def test_strict_blocking_when_fallback_disabled(self, monkeypatch):
        """With ``sovereignty_fallback_to_local=False``, the guard raises
        instead of rerouting. The guarded embedder must propagate — no
        silent external leak, no silent swallow."""
        from aim.config import get_settings
        from aim.utils.sovereignty import SovereigntyViolation

        s = get_settings()
        monkeypatch.setattr(s, "sovereignty_mode", "strict")
        monkeypatch.setattr(s, "sovereignty_allowed_classifications", ["PUBLIC", "INTERNAL"])
        monkeypatch.setattr(s, "external_llm_providers", ["openai"])
        monkeypatch.setattr(s, "sovereignty_fallback_to_local", False)

        external = _FakeEmbedder("openai")
        guarded = SovereigntyGuardedEmbeddingProvider(external, provider_name="openai")

        with pytest.raises(SovereigntyViolation):
            await guarded.embed("SSN: 123-45-6789")

        assert external.embed_calls == []

    @pytest.mark.asyncio
    async def test_local_provider_passes_through_unguarded(self, monkeypatch):
        """A ``local`` embedding provider doesn't need the guard — it's
        already residency-safe. The factory skips the wrapper for ``local``
        so no per-embed classifier burn. This test verifies the wrapper
        doesn't block local traffic when it IS applied (belt-and-braces)."""
        from aim.config import get_settings

        s = get_settings()
        monkeypatch.setattr(s, "sovereignty_mode", "strict")
        monkeypatch.setattr(s, "sovereignty_allowed_classifications", ["PUBLIC"])
        monkeypatch.setattr(s, "external_llm_providers", ["openai", "anthropic"])

        local_delegate = _FakeEmbedder("local")
        # Guard provider_name is "local" — guard's local-provider check
        # bypasses classification entirely.
        guarded = SovereigntyGuardedEmbeddingProvider(local_delegate, provider_name="local")
        await guarded.embed("SSN: 123-45-6789")
        assert local_delegate.embed_calls == ["SSN: 123-45-6789"]


class TestFactoryWiring:
    def test_external_embedding_provider_is_wrapped(self, monkeypatch):
        """``get_embedding_provider()`` must return a sovereignty-guarded
        instance for external (``openai``) providers."""
        from aim.config import get_settings
        from aim.llm.factory import get_embedding_provider, reset_providers

        reset_providers()
        s = get_settings()
        monkeypatch.setattr(s, "embedding_provider", "openai")
        monkeypatch.setattr(s, "embedding_base_url", "")
        monkeypatch.setattr(s, "openai_api_key", "sk-test")

        provider = get_embedding_provider()
        try:
            assert isinstance(provider, SovereigntyGuardedEmbeddingProvider)
        finally:
            reset_providers()

    def test_local_embedding_provider_is_wrapped_but_unblocked(self, monkeypatch):
        """Even ``local`` providers go through the wrapper — the wrapper's
        ``_pick_delegate`` will see ``provider_name="local"`` and the guard
        returns ``local_provider`` decision, so the delegate runs as normal.
        We accept the trivial wrapping cost for uniformity."""
        from aim.config import get_settings
        from aim.llm.factory import get_embedding_provider, reset_providers

        reset_providers()
        s = get_settings()
        monkeypatch.setattr(s, "embedding_provider", "local")
        monkeypatch.setattr(s, "embedding_base_url", "http://localhost:11434/v1")

        provider = get_embedding_provider()
        try:
            assert isinstance(provider, SovereigntyGuardedEmbeddingProvider)
        finally:
            reset_providers()
