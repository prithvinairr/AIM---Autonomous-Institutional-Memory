"""Provider factory — reads config and returns the right LLM/embedding provider.

Configuration:
    LLM_PROVIDER=anthropic          # default — uses Anthropic Claude
    LLM_PROVIDER=openai             # uses OpenAI GPT
    LLM_PROVIDER=local              # uses any OpenAI-compatible local server
    LLM_BASE_URL=http://...         # required for 'local', optional for 'openai'

    EMBEDDING_PROVIDER=openai       # default — OpenAI embeddings
    EMBEDDING_PROVIDER=local        # any OpenAI-compatible embedding server
    EMBEDDING_BASE_URL=http://...   # required for 'local'
"""
from __future__ import annotations

import asyncio

import structlog

from aim.llm.base import EmbeddingProvider, LLMProvider, LLMResponse

log = structlog.get_logger(__name__)

_llm_instance: LLMProvider | None = None
_embedding_instance: EmbeddingProvider | None = None


class CircuitBreakerLLMProvider(LLMProvider):
    """Wraps an LLM provider with a circuit breaker keyed by provider name.

    When the downstream LLM is failing repeatedly the breaker trips OPEN and
    subsequent calls fail fast with ``CircuitOpenError`` instead of queueing
    behind the rate limiter or holding open a slow TCP socket.  This protects
    the rest of the pipeline (decomposer, synthesizer, reranker, evaluator,
    reasoning_agent) from cascade failure.

    Streaming is probed on the *first* chunk — a broken provider typically
    fails during the initial connection, so we count that as the breaker's
    success signal and then pass the rest of the generator through untouched.
    """

    def __init__(self, delegate: LLMProvider, breaker_name: str) -> None:
        self._delegate = delegate
        self._breaker_name = breaker_name

    def _breaker(self):
        from aim.utils.circuit_breaker import get_breaker
        return get_breaker(self._breaker_name)

    async def invoke(self, messages: list[dict], **kwargs) -> LLMResponse:
        return await self._breaker().call(self._delegate.invoke, messages, **kwargs)

    async def stream(self, messages: list[dict], **kwargs):
        # Probe the first chunk under the breaker to register success/failure,
        # then yield the rest directly. We can't run the whole generator inside
        # ``breaker.call`` because that would buffer the entire response before
        # any token reaches the client — streaming would stop streaming.
        breaker = self._breaker()

        async def _first_chunk_probe():
            gen = self._delegate.stream(messages, **kwargs)
            first = await gen.__anext__()
            return first, gen

        try:
            first, gen = await breaker.call(_first_chunk_probe)
        except StopAsyncIteration:
            return
        yield first
        async for chunk in gen:
            yield chunk

    async def health_check(self) -> bool:
        return await self._delegate.health_check()


class RateLimitedLLMProvider(LLMProvider):
    """Wraps an LLM provider with distributed rate limiting.

    Uses a Redis-based sliding window counter for cross-process coordination
    (multi-worker deployments), combined with a local ``asyncio.Semaphore``
    for per-process burst control.  Falls back to local-only limiting when
    Redis is unavailable — ensures zero downtime on Redis failures.
    """

    _REDIS_KEY = "aim:llm:concurrent_calls"
    _REDIS_TTL_SECONDS = 10  # auto-expire stale counters

    def __init__(self, delegate: LLMProvider, max_concurrent: int = 10) -> None:
        self._delegate = delegate
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent
        log.info("llm.rate_limiter.init", max_concurrent=max_concurrent)

    async def _acquire_distributed(self) -> bool:
        """Try to acquire a distributed slot via Redis INCR.

        Returns True if acquired (caller must release), False if Redis is
        unavailable or at capacity (falls through to local-only limiting).
        """
        try:
            from aim.utils.cache import get_response_cache
            cache = get_response_cache()
            if cache._redis is None:
                return False
            count = await cache._redis.incr(self._REDIS_KEY)
            await cache._redis.expire(self._REDIS_KEY, self._REDIS_TTL_SECONDS)
            if count > self._max_concurrent:
                await cache._redis.decr(self._REDIS_KEY)
                return False
            return True
        except Exception:
            return False

    async def _release_distributed(self) -> None:
        """Release a distributed slot."""
        try:
            from aim.utils.cache import get_response_cache
            cache = get_response_cache()
            if cache._redis is not None:
                await cache._redis.decr(self._REDIS_KEY)
        except Exception:
            pass

    async def invoke(self, messages: list[dict], **kwargs) -> LLMResponse:
        distributed = await self._acquire_distributed()
        try:
            async with self._semaphore:
                return await self._delegate.invoke(messages, **kwargs)
        finally:
            if distributed:
                await self._release_distributed()

    async def stream(self, messages: list[dict], **kwargs):
        distributed = await self._acquire_distributed()
        try:
            async with self._semaphore:
                async for chunk in self._delegate.stream(messages, **kwargs):
                    yield chunk
        finally:
            if distributed:
                await self._release_distributed()

    async def health_check(self) -> bool:
        return await self._delegate.health_check()


class SovereigntyGuardedLLMProvider(LLMProvider):
    """Wraps an LLM provider with data sovereignty enforcement.

    Checks every ``invoke``/``stream`` call against the configured
    sovereignty policy before dispatching to the delegate.  In strict
    mode with ``sovereignty_fallback_to_local=True``, calls flagged for
    reroute are dispatched to a local OpenAI-compatible provider instead
    of the external delegate — so classified data never crosses the
    external boundary.  Otherwise strict violations raise
    ``SovereigntyViolation``.
    """

    def __init__(self, delegate: LLMProvider, provider_name: str) -> None:
        self._delegate = delegate
        self._provider_name = provider_name
        self._local: LLMProvider | None = None

    def _local_provider(self) -> LLMProvider | None:
        """Lazily construct a local OpenAI-compatible provider for reroutes."""
        if self._local is not None:
            return self._local
        from aim.config import get_settings
        settings = get_settings()
        if not settings.llm_base_url:
            return None
        from aim.llm.openai_provider import OpenAILLMProvider
        self._local = OpenAILLMProvider(
            api_key=settings.openai_api_key or "not-needed",
            model=settings.llm_model,
            base_url=settings.llm_base_url,
        )
        log.info("llm.sovereignty.local_provider_ready", base_url=settings.llm_base_url)
        return self._local

    def _pick_delegate(self, messages: list[dict]) -> LLMProvider:
        from aim.utils.sovereignty import get_sovereignty_guard
        guard = get_sovereignty_guard()
        decision = guard.check(messages, self._provider_name)
        if decision.reason.startswith("rerouted_to_local"):
            local = self._local_provider()
            if local is not None:
                return local
        return self._delegate

    async def invoke(self, messages: list[dict], **kwargs) -> LLMResponse:
        target = self._pick_delegate(messages)
        return await target.invoke(messages, **kwargs)

    async def stream(self, messages: list[dict], **kwargs):
        target = self._pick_delegate(messages)
        async for chunk in target.stream(messages, **kwargs):
            yield chunk

    async def health_check(self) -> bool:
        return await self._delegate.health_check()


class SovereigntyGuardedEmbeddingProvider(EmbeddingProvider):
    """Symmetric sovereignty guard for embeddings.

    Panel audit (δ.2, 2026-04-18) flagged that only *completion* calls ran
    through :class:`SovereigntyGuardedLLMProvider`. Embedding calls — which
    send the same raw document text to the same external providers —
    bypassed the check entirely. A document classified RESTRICTED could
    leak to OpenAI as embedding input with no gate.

    This wrapper closes the gap. Each ``embed`` / ``embed_batch`` call
    runs the same :class:`SovereigntyGuard.check` that LLM calls use,
    projecting text through the guard's ``messages`` API. When the guard
    reroutes to local (strict mode + fallback enabled), the embedding
    dispatches to a lazily-constructed local OpenAI-compatible embedder
    instead. When the guard raises, we propagate — consistent with the
    LLM-side contract.

    Batch policy: if ANY text in a batch triggers a reroute, the **entire**
    batch is rerouted to local. Splitting the batch across providers is
    tempting but gives up the dimension guarantee (local and external
    models often produce different-sized vectors) and complicates token
    accounting. "One classified text forces the batch local" is the safe
    default; operators who want finer-grained routing can pre-classify
    upstream.
    """

    def __init__(self, delegate: EmbeddingProvider, provider_name: str) -> None:
        self._delegate = delegate
        self._provider_name = provider_name
        self._local: EmbeddingProvider | None = None

    def _local_embedder(self) -> EmbeddingProvider | None:
        """Lazily construct a local OpenAI-compatible embedder for reroutes."""
        if self._local is not None:
            return self._local
        from aim.config import get_settings

        settings = get_settings()
        base_url = settings.embedding_base_url or settings.llm_base_url
        if not base_url:
            return None
        from aim.llm.openai_provider import OpenAIEmbeddingProvider

        self._local = OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key or "not-needed",
            model=settings.embedding_model,
            dim=settings.embedding_dimension,
            base_url=base_url,
        )
        log.info(
            "embedding.sovereignty.local_provider_ready",
            base_url=base_url,
        )
        return self._local

    def _pick_delegate(self, texts: list[str]) -> EmbeddingProvider:
        from aim.utils.sovereignty import get_sovereignty_guard

        guard = get_sovereignty_guard()
        # Project each text through the guard's ``messages`` shape. Any
        # single reroute decision flips the whole batch to local — see
        # batch policy in the class docstring.
        for text in texts:
            if not text:
                continue
            decision = guard.check(
                [{"role": "user", "content": text}],
                self._provider_name,
            )
            if decision.reason.startswith("rerouted_to_local"):
                local = self._local_embedder()
                if local is not None:
                    return local
        return self._delegate

    async def embed(self, text: str) -> list[float]:
        target = self._pick_delegate([text])
        return await target.embed(text)

    async def embed_batch(self, texts: list[str]) -> tuple[list[list[float]], int]:
        target = self._pick_delegate(texts)
        return await target.embed_batch(texts)

    def dimension(self) -> int:
        return self._delegate.dimension()


def get_llm_provider() -> LLMProvider:
    """Return the configured LLM provider (singleton, rate-limited)."""
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance

    from aim.config import get_settings
    settings = get_settings()
    provider = settings.llm_provider.lower()

    raw_provider: LLMProvider

    if provider == "anthropic":
        from aim.llm.anthropic_provider import AnthropicLLMProvider
        raw_provider = AnthropicLLMProvider(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
        )
    elif provider == "openai":
        from aim.llm.openai_provider import OpenAILLMProvider
        raw_provider = OpenAILLMProvider(
            api_key=settings.openai_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url or None,
        )
    elif provider == "local":
        from aim.llm.openai_provider import OpenAILLMProvider
        if not settings.llm_base_url:
            raise ValueError(
                "LLM_PROVIDER=local requires LLM_BASE_URL "
                "(e.g. http://localhost:11434/v1 for Ollama)"
            )
        raw_provider = OpenAILLMProvider(
            api_key=settings.openai_api_key or "not-needed",
            model=settings.llm_model,
            base_url=settings.llm_base_url,
        )
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER={provider!r}. "
            "Supported: anthropic, openai, local"
        )

    # Wrap: raw → sovereignty guard → rate limiter → circuit breaker.
    # Breaker is the outermost layer so it can reject cascade-failing
    # requests before they consume a semaphore slot or trigger a policy
    # check — the fastest possible fail path.
    guarded = SovereigntyGuardedLLMProvider(raw_provider, provider_name=provider)
    rate_limited = RateLimitedLLMProvider(
        guarded,
        max_concurrent=settings.max_concurrent_llm_calls,
    )
    _llm_instance = CircuitBreakerLLMProvider(
        rate_limited,
        breaker_name=f"llm_{provider}",
    )

    log.info(
        "llm.provider_initialized",
        provider=provider,
        model=settings.llm_model,
        base_url=settings.llm_base_url or "(default)",
        max_concurrent=settings.max_concurrent_llm_calls,
    )
    return _llm_instance


def get_embedding_provider() -> EmbeddingProvider:
    """Return the configured embedding provider (singleton, sovereignty-guarded)."""
    global _embedding_instance
    if _embedding_instance is not None:
        return _embedding_instance

    from aim.config import get_settings
    settings = get_settings()
    provider = settings.embedding_provider.lower()

    if provider in ("openai", "local"):
        from aim.llm.openai_provider import OpenAIEmbeddingProvider
        base_url = settings.embedding_base_url or None
        if provider == "local" and not base_url:
            raise ValueError(
                "EMBEDDING_PROVIDER=local requires EMBEDDING_BASE_URL "
                "(e.g. http://localhost:11434/v1 for Ollama)"
            )
        raw_provider: EmbeddingProvider = OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key or "not-needed",
            model=settings.embedding_model,
            dim=settings.embedding_dimension,
            base_url=base_url,
        )
    else:
        raise ValueError(
            f"Unknown EMBEDDING_PROVIDER={provider!r}. "
            "Supported: openai, local"
        )

    # Wrap external embedders in the same sovereignty guard used for LLM
    # completions. ``local`` providers pass through unguarded — they already
    # satisfy residency by definition and the guard would be a no-op that
    # only burns a classifier pass per embed.
    _embedding_instance = SovereigntyGuardedEmbeddingProvider(
        raw_provider,
        provider_name=provider,
    )

    log.info(
        "embedding.provider_initialized",
        provider=provider,
        model=settings.embedding_model,
        base_url=settings.embedding_base_url or "(default)",
        sovereignty_guarded=True,
    )
    return _embedding_instance


def reset_providers() -> None:
    """Reset singletons (for testing)."""
    global _llm_instance, _embedding_instance
    _llm_instance = None
    _embedding_instance = None
