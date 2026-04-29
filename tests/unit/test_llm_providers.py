"""Unit tests for the pluggable LLM/embedding provider abstraction."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.llm.base import EmbeddingProvider, LLMProvider, LLMResponse, LLMTokenChunk
from aim.llm.factory import get_llm_provider, get_embedding_provider, reset_providers


# ── Factory tests ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset():
    """Reset singletons between tests."""
    reset_providers()
    yield
    reset_providers()


def _mock_settings(**overrides):
    defaults = {
        "llm_provider": "anthropic",
        "llm_base_url": "",
        "anthropic_api_key": "sk-test",
        "openai_api_key": "sk-oai-test",
        "llm_model": "claude-opus-4-6",
        "llm_temperature": 0.1,
        "llm_max_tokens": 4096,
        "embedding_provider": "openai",
        "embedding_base_url": "",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimension": 1536,
        "embedding_cache_size": 100,
        "max_concurrent_llm_calls": 10,
        "sovereignty_mode": "off",
        "sovereignty_allowed_classifications": ["PUBLIC", "INTERNAL"],
        "external_llm_providers": ["anthropic", "openai"],
        "restricted_fields": ["ssn", "password"],
        "confidential_fields": ["email", "phone"],
        "llm_max_data_classification": "internal",
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def test_factory_returns_anthropic_by_default():
    with patch("aim.config.get_settings", return_value=_mock_settings()):
        provider = get_llm_provider()
    from aim.llm.anthropic_provider import AnthropicLLMProvider
    from aim.llm.factory import (
        CircuitBreakerLLMProvider,
        RateLimitedLLMProvider,
        SovereigntyGuardedLLMProvider,
    )
    # Chain: CircuitBreaker → RateLimited → SovereigntyGuarded → Anthropic
    assert isinstance(provider, CircuitBreakerLLMProvider)
    assert isinstance(provider._delegate, RateLimitedLLMProvider)
    assert isinstance(provider._delegate._delegate, SovereigntyGuardedLLMProvider)
    assert isinstance(provider._delegate._delegate._delegate, AnthropicLLMProvider)


def test_factory_returns_openai_llm():
    with patch("aim.config.get_settings", return_value=_mock_settings(llm_provider="openai")):
        provider = get_llm_provider()
    from aim.llm.openai_provider import OpenAILLMProvider
    from aim.llm.factory import (
        CircuitBreakerLLMProvider,
        RateLimitedLLMProvider,
        SovereigntyGuardedLLMProvider,
    )
    assert isinstance(provider, CircuitBreakerLLMProvider)
    assert isinstance(provider._delegate, RateLimitedLLMProvider)
    assert isinstance(provider._delegate._delegate, SovereigntyGuardedLLMProvider)
    assert isinstance(provider._delegate._delegate._delegate, OpenAILLMProvider)


def test_factory_local_requires_base_url():
    with patch("aim.config.get_settings", return_value=_mock_settings(llm_provider="local", llm_base_url="")):
        with pytest.raises(ValueError, match="LLM_BASE_URL"):
            get_llm_provider()


def test_factory_local_with_base_url():
    with patch("aim.config.get_settings", return_value=_mock_settings(
        llm_provider="local", llm_base_url="http://localhost:11434/v1"
    )):
        provider = get_llm_provider()
    from aim.llm.openai_provider import OpenAILLMProvider
    from aim.llm.factory import (
        CircuitBreakerLLMProvider,
        RateLimitedLLMProvider,
        SovereigntyGuardedLLMProvider,
    )
    assert isinstance(provider, CircuitBreakerLLMProvider)
    assert isinstance(provider._delegate, RateLimitedLLMProvider)
    assert isinstance(provider._delegate._delegate, SovereigntyGuardedLLMProvider)
    assert isinstance(provider._delegate._delegate._delegate, OpenAILLMProvider)


def test_factory_unknown_provider_raises():
    with patch("aim.config.get_settings", return_value=_mock_settings(llm_provider="unknown")):
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
            get_llm_provider()


def test_factory_singleton():
    with patch("aim.config.get_settings", return_value=_mock_settings()):
        p1 = get_llm_provider()
        p2 = get_llm_provider()
    assert p1 is p2


def test_embedding_factory_openai():
    with patch("aim.config.get_settings", return_value=_mock_settings()):
        provider = get_embedding_provider()
    from aim.llm.factory import SovereigntyGuardedEmbeddingProvider
    from aim.llm.openai_provider import OpenAIEmbeddingProvider
    # δ.2: factory wraps every embedder in the sovereignty guard so
    # classified text can't leak to OpenAI without a classification pass.
    assert isinstance(provider, SovereigntyGuardedEmbeddingProvider)
    assert isinstance(provider._delegate, OpenAIEmbeddingProvider)


def test_embedding_factory_local_requires_base_url():
    with patch("aim.config.get_settings", return_value=_mock_settings(
        embedding_provider="local", embedding_base_url=""
    )):
        with pytest.raises(ValueError, match="EMBEDDING_BASE_URL"):
            get_embedding_provider()


def test_embedding_factory_local_with_base_url():
    with patch("aim.config.get_settings", return_value=_mock_settings(
        embedding_provider="local", embedding_base_url="http://localhost:11434/v1"
    )):
        provider = get_embedding_provider()
    from aim.llm.factory import SovereigntyGuardedEmbeddingProvider
    from aim.llm.openai_provider import OpenAIEmbeddingProvider
    assert isinstance(provider, SovereigntyGuardedEmbeddingProvider)
    assert isinstance(provider._delegate, OpenAIEmbeddingProvider)
    assert provider.dimension() == 1536


def test_embedding_factory_unknown_raises():
    with patch("aim.config.get_settings", return_value=_mock_settings(embedding_provider="bad")):
        with pytest.raises(ValueError, match="Unknown EMBEDDING_PROVIDER"):
            get_embedding_provider()


def test_reset_clears_singletons():
    with patch("aim.config.get_settings", return_value=_mock_settings()):
        p1 = get_llm_provider()
    reset_providers()
    with patch("aim.config.get_settings", return_value=_mock_settings()):
        p2 = get_llm_provider()
    assert p1 is not p2


# ── LLMResponse / LLMTokenChunk ─────────────────────────────────────────────


def test_llm_response_fields():
    resp = LLMResponse(content="hello", input_tokens=10, output_tokens=5, model="test")
    assert resp.content == "hello"
    assert resp.input_tokens == 10
    assert resp.output_tokens == 5


def test_llm_token_chunk_final():
    chunk = LLMTokenChunk(content="", input_tokens=100, output_tokens=50, is_final=True)
    assert chunk.is_final
    assert chunk.input_tokens == 100


# ── AnthropicLLMProvider ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anthropic_invoke():
    from aim.llm.anthropic_provider import AnthropicLLMProvider

    mock_response = MagicMock()
    mock_response.content = "test answer"
    mock_response.usage_metadata = {"input_tokens": 100, "output_tokens": 50}

    with patch("aim.llm.anthropic_provider.ChatAnthropic") as MockCls:
        mock_instance = MagicMock()
        mock_instance.ainvoke = AsyncMock(return_value=mock_response)
        mock_instance.bind = MagicMock(return_value=mock_instance)
        MockCls.return_value = mock_instance
        provider = AnthropicLLMProvider(api_key="sk-test", model="claude-test")
        result = await provider.invoke(
            [{"role": "user", "content": "hello"}],
            temperature=0.5,
            max_tokens=100,
        )

    assert result.content == "test answer"
    assert result.input_tokens == 100
    assert result.output_tokens == 50


@pytest.mark.asyncio
async def test_anthropic_stream():
    from aim.llm.anthropic_provider import AnthropicLLMProvider

    provider = AnthropicLLMProvider(api_key="sk-test", model="claude-test")

    chunk1 = MagicMock()
    chunk1.content = "hello "
    chunk1.usage_metadata = None

    chunk2 = MagicMock()
    chunk2.content = "world"
    chunk2.usage_metadata = {"input_tokens": 80, "output_tokens": 20}

    async def fake_stream(messages):
        yield chunk1
        yield chunk2

    with patch("aim.llm.anthropic_provider.ChatAnthropic") as MockCls:
        MockCls.return_value.astream = fake_stream
        chunks = []
        async for c in provider.stream(
            [{"role": "user", "content": "hi"}],
        ):
            chunks.append(c)

    # 2 content chunks + 1 final
    assert len(chunks) == 3
    assert chunks[0].content == "hello "
    assert chunks[1].content == "world"
    assert chunks[2].is_final
    assert chunks[2].input_tokens == 80


@pytest.mark.asyncio
async def test_anthropic_health_check_success():
    from aim.llm.anthropic_provider import AnthropicLLMProvider

    mock_response = MagicMock()
    mock_response.content = "pong"

    with patch("aim.llm.anthropic_provider.ChatAnthropic") as MockCls:
        mock_instance = MagicMock()
        mock_instance.ainvoke = AsyncMock(return_value=mock_response)
        mock_instance.bind = MagicMock(return_value=mock_instance)
        MockCls.return_value = mock_instance
        provider = AnthropicLLMProvider(api_key="sk-test", model="claude-test")
        result = await provider.health_check()

    assert result is True


@pytest.mark.asyncio
async def test_anthropic_health_check_failure():
    from aim.llm.anthropic_provider import AnthropicLLMProvider

    with patch("aim.llm.anthropic_provider.ChatAnthropic") as MockCls:
        mock_instance = MagicMock()
        mock_instance.ainvoke = AsyncMock(side_effect=ConnectionError("down"))
        mock_instance.bind = MagicMock(return_value=mock_instance)
        MockCls.return_value = mock_instance
        provider = AnthropicLLMProvider(api_key="sk-test", model="claude-test")
        result = await provider.health_check()

    assert result is False


# ── Cross-modal re-ranking ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cross_modal_rerank_boosts_shared_entities():
    """Sources found in both graph and vector should be boosted."""
    from unittest.mock import patch
    from aim.agents.nodes.synthesizer import _cross_modal_rerank
    from aim.agents.reranker import NoopReranker, reset_reranker
    from aim.agents.state import AgentState
    from aim.schemas.provenance import SourceReference, SourceType
    from uuid import uuid4

    # Graph source for "Auth Service"
    graph_src = SourceReference(
        source_type=SourceType.NEO4J_GRAPH,
        uri="neo4j://node/1",
        title="Auth Service",
        content_snippet="Auth owned by platform",
        confidence=0.90,
    )
    # Vector source also titled "Auth Service"
    vec_src = SourceReference(
        source_type=SourceType.PINECONE_VECTOR,
        uri="pinecone://v1",
        title="Auth Service",
        content_snippet="Auth service docs",
        confidence=0.80,
    )
    # Unrelated vector source
    other_src = SourceReference(
        source_type=SourceType.PINECONE_VECTOR,
        uri="pinecone://v2",
        title="Unrelated Doc",
        content_snippet="Something else",
        confidence=0.85,
    )
    state = AgentState(
        query_id=uuid4(),
        original_query="test",
        sources={
            graph_src.source_id: graph_src,
            vec_src.source_id: vec_src,
            other_src.source_id: other_src,
        },
    )
    # Use NoopReranker to isolate the cross-modal fusion logic
    reset_reranker()
    with patch("aim.agents.reranker.get_reranker", return_value=NoopReranker()):
        ranked = await _cross_modal_rerank(state)
    reset_reranker()
    scores = dict(ranked)

    # The matched graph and vector sources should be boosted
    assert scores[graph_src.source_id] > 0.90 * 1.0  # boosted above base
    assert scores[vec_src.source_id] > 0.80 * 0.85  # boosted above base

    # The unrelated source should NOT be boosted
    assert scores[other_src.source_id] == pytest.approx(0.85 * 0.85)


@pytest.mark.asyncio
async def test_cross_modal_rerank_empty_state():
    from unittest.mock import patch
    from aim.agents.nodes.synthesizer import _cross_modal_rerank
    from aim.agents.reranker import NoopReranker, reset_reranker
    from aim.agents.state import AgentState
    from uuid import uuid4

    reset_reranker()
    state = AgentState(query_id=uuid4(), original_query="test")
    with patch("aim.agents.reranker.get_reranker", return_value=NoopReranker()):
        ranked = await _cross_modal_rerank(state)
    reset_reranker()
    assert ranked == []
