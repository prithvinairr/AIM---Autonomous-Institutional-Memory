"""Async Pinecone client — LRU embedding cache, circuit breaker, typed returns.

Key design choices
──────────────────
* ``_get_pinecone_index()`` is async and offloads all Pinecone SDK I/O to a
  thread-pool executor so it never blocks the event loop.

* ``_embed()`` uses a futures-based deduplication pattern: the *first* coroutine
  to request a given text becomes the producer; concurrent coroutines for the
  same key await the producer's future instead of making duplicate OpenAI calls.

* ``batch_embed()`` sends all texts in a single OpenAI API call, checks the LRU
  cache first, and writes all results back in one lock acquisition — reducing
  N serial embedding round-trips to 1.

* ``query_with_embedding()`` accepts a precomputed embedding so the retriever
  can embed all sub-queries in one batch then fan-out Pinecone queries in
  parallel without redundant embedding work.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

import structlog
from cachetools import LRUCache
from openai import AsyncOpenAI
from pinecone import Pinecone, ServerlessSpec
from tenacity import retry, stop_after_attempt, wait_exponential

from aim.config import get_settings
from aim.utils.metrics import EMBEDDING_CACHE_HITS, EMBEDDING_LATENCY, PINECONE_QUERY_LATENCY

log = structlog.get_logger(__name__)

# ── Embedding cache (module-level, shared across all PineconeClient instances) ─

_embed_cache: LRUCache = LRUCache(maxsize=1)       # resized at first use
_embed_lock: asyncio.Lock | None = None
_embed_cache_initialized = False

# Futures-based in-flight deduplication: text SHA-256 → Future[embedding]
# Prevents N concurrent coroutines from all calling OpenAI for the same text.
_pending_embeds: dict[str, asyncio.Future[list[float]]] = {}


def _get_embed_lock() -> asyncio.Lock:
    global _embed_lock
    if _embed_lock is None:
        _embed_lock = asyncio.Lock()
    return _embed_lock


def _init_embed_cache() -> None:
    global _embed_cache, _embed_cache_initialized
    if not _embed_cache_initialized:
        _embed_cache = LRUCache(maxsize=get_settings().embedding_cache_size)
        _embed_cache_initialized = True


# ── Pinecone index singleton (lazy, async-safe) ───────────────────────────────

_pinecone_index: Any | None = None
_pinecone_init_lock: asyncio.Lock | None = None


def _get_pinecone_init_lock() -> asyncio.Lock:
    global _pinecone_init_lock
    if _pinecone_init_lock is None:
        _pinecone_init_lock = asyncio.Lock()
    return _pinecone_init_lock


async def _get_pinecone_index() -> Any:
    """Return (lazily initialise) the shared Pinecone Index.

    All blocking Pinecone SDK calls are offloaded to a thread-pool executor
    so the asyncio event loop is never stalled on network I/O.
    """
    global _pinecone_index
    if _pinecone_index is not None:
        return _pinecone_index

    async with _get_pinecone_init_lock():
        if _pinecone_index is not None:          # double-checked locking
            return _pinecone_index

        settings = get_settings()
        loop = asyncio.get_running_loop()

        def _sync_init() -> Any:
            pc = Pinecone(api_key=settings.pinecone_api_key)
            existing = {idx["name"] for idx in pc.list_indexes()}
            if settings.pinecone_index_name not in existing:
                log.info("pinecone.creating_index", name=settings.pinecone_index_name)
                pc.create_index(
                    name=settings.pinecone_index_name,
                    dimension=settings.embedding_dimension,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region=settings.pinecone_environment),
                )
            return pc.Index(settings.pinecone_index_name)

        _pinecone_index = await loop.run_in_executor(None, _sync_init)
        log.info("pinecone.index_ready", name=settings.pinecone_index_name)

    return _pinecone_index


# ── Client ────────────────────────────────────────────────────────────────────

class PineconeClient:
    def __init__(self) -> None:
        _init_embed_cache()
        self._settings = get_settings()
        self._openai = AsyncOpenAI(api_key=self._settings.openai_api_key)

    async def _get_index(self) -> Any:
        return await _get_pinecone_index()

    # ── Query ─────────────────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    async def query(
        self,
        text: str,
        top_k: int = 10,
        score_threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> list[dict[str, Any]]:
        embedding = await self._embed(text)
        return await self.query_with_embedding(
            embedding,
            top_k=top_k,
            score_threshold=score_threshold,
            filters=filters,
            namespace=namespace,
        )

    async def query_with_embedding(
        self,
        embedding: list[float],
        top_k: int = 10,
        score_threshold: float = 0.0,
        filters: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run Pinecone ANN search with a precomputed embedding.

        Accepts a precomputed embedding so callers can batch-embed multiple
        texts up-front (one OpenAI call) then fan-out queries in parallel.
        """
        t0 = time.perf_counter()
        index = await self._get_index()
        ns = namespace or self._settings.pinecone_namespace

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: index.query(
                vector=embedding,
                top_k=top_k,
                include_metadata=True,
                namespace=ns,
                filter=filters or None,
            ),
        )
        PINECONE_QUERY_LATENCY.observe(time.perf_counter() - t0)

        return [
            {
                "id": m["id"],
                "score": float(m["score"]),
                "metadata": m.get("metadata", {}),
            }
            for m in response.get("matches", [])
            if float(m["score"]) >= score_threshold
        ]

    # ── Upsert / Delete ───────────────────────────────────────────────────────

    async def upsert(
        self,
        vectors: list[tuple[str, list[float], dict[str, Any]]],
        namespace: str | None = None,
    ) -> int:
        ns = namespace or self._settings.pinecone_namespace
        records = [{"id": vid, "values": vec, "metadata": meta} for vid, vec, meta in vectors]
        index = await self._get_index()
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: index.upsert(vectors=records, namespace=ns)
        )
        upserted: int = result.get("upserted_count", 0)
        log.info("pinecone.upserted", count=upserted)
        return upserted

    async def upsert_text(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> None:
        embedding = await self._embed(text)
        meta = {"text": text[:40960], **(metadata or {})}
        await self.upsert([(doc_id, embedding, meta)], namespace=namespace)

    async def delete(self, ids: list[str], namespace: str | None = None) -> None:
        ns = namespace or self._settings.pinecone_namespace
        index = await self._get_index()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: index.delete(ids=ids, namespace=ns))

    async def health_check(self) -> bool:
        try:
            index = await self._get_index()
            loop = asyncio.get_running_loop()
            stats = await loop.run_in_executor(None, index.describe_index_stats)
            return stats is not None
        except Exception as exc:
            log.error("pinecone.health_check_failed", error=str(exc))
            return False

    # ── Embeddings ────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.5, max=4), reraise=True)
    async def _embed(self, text: str) -> list[float]:
        """Embed a single text with futures-based in-flight deduplication.

        If two coroutines request the same text simultaneously, only one calls
        OpenAI; the other awaits the first one's result.
        """
        cache_key = hashlib.sha256(text.encode()).hexdigest()
        lock = _get_embed_lock()
        my_future: asyncio.Future[list[float]] | None = None

        async with lock:
            # 1. Real cache hit
            if (val := _embed_cache.get(cache_key)) is not None:
                EMBEDDING_CACHE_HITS.labels(result="hit").inc()
                return val

            # 2. Another coroutine is already producing this embedding
            if cache_key in _pending_embeds:
                waiter = _pending_embeds[cache_key]
            else:
                # 3. We're the producer — register a future as a placeholder
                my_future = asyncio.get_running_loop().create_future()
                _pending_embeds[cache_key] = my_future
                waiter = None

        # Waiter path — wait outside the lock
        if waiter is not None:
            EMBEDDING_CACHE_HITS.labels(result="hit").inc()
            return await waiter

        # Producer path
        EMBEDDING_CACHE_HITS.labels(result="miss").inc()
        t0 = time.perf_counter()
        try:
            response = await self._openai.embeddings.create(
                model=self._settings.embedding_model,
                input=text[:32768],
                encoding_format="float",
            )
            EMBEDDING_LATENCY.observe(time.perf_counter() - t0)
            embedding: list[float] = response.data[0].embedding

            async with lock:
                _embed_cache[cache_key] = embedding
                _pending_embeds.pop(cache_key, None)

            assert my_future is not None
            if not my_future.done():
                my_future.set_result(embedding)

            return embedding

        except Exception as exc:
            async with lock:
                _pending_embeds.pop(cache_key, None)
            if my_future and not my_future.done():
                my_future.set_exception(exc)
            raise

    async def batch_embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """Embed multiple texts in a single OpenAI API call.

        Returns ``(embeddings, tokens_used)`` so callers can accumulate
        embedding token counts for cost tracking.

        Checks the LRU cache first; only the cache-miss subset is sent to
        OpenAI. All results are written back to the cache in one lock
        acquisition. Reduces N serial embedding calls to at most 1.

        Cache hits contribute 0 tokens (no API call made for them).
        """
        if not texts:
            return [], 0

        cache_keys = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
        results: list[list[float] | None] = [None] * len(texts)
        miss_indices: list[int] = []

        lock = _get_embed_lock()
        async with lock:
            for i, key in enumerate(cache_keys):
                if (val := _embed_cache.get(key)) is not None:
                    results[i] = val
                    EMBEDDING_CACHE_HITS.labels(result="hit").inc()
                else:
                    miss_indices.append(i)

        if not miss_indices:
            return results, 0  # type: ignore[return-value]

        miss_texts = [texts[i][:32768] for i in miss_indices]
        EMBEDDING_CACHE_HITS.labels(result="miss").inc()
        t0 = time.perf_counter()

        response = await self._openai.embeddings.create(
            model=self._settings.embedding_model,
            input=miss_texts,
            encoding_format="float",
        )
        EMBEDDING_LATENCY.observe(time.perf_counter() - t0)

        tokens_used: int = response.usage.total_tokens if response.usage else 0

        async with lock:
            for j, idx in enumerate(miss_indices):
                emb = response.data[j].embedding
                results[idx] = emb
                _embed_cache[cache_keys[idx]] = emb

        return results, tokens_used  # type: ignore[return-value]
