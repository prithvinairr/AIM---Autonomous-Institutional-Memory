"""AIM – Autonomous Institutional Memory — application entry point.

Startup sequence:
  1. Configure structured logging
  2. Wire OpenTelemetry tracing
  3. Register Prometheus app-info metric
  4. Connect Redis cache + conversation store
  5. Run Neo4j schema migrations (versioned, idempotent)
  6. Start background ingest worker
  7. Start background cache-reaping task

Shutdown sequence:
  1. Cancel background tasks (reaper + ingest worker)
  2. Close shared Neo4j driver
  3. Close Redis connections (cache + conversation store)
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aim.api.middleware import RequestBodyLimitMiddleware, RequestContextMiddleware
from aim.api.routes import graph, health, query, webhooks
from aim.api.routes import conversations, feedback, mcp_sse
from aim.config import get_settings
from aim.utils.logging import configure_logging
from aim.utils.metrics import init_app_info

configure_logging()
log = structlog.get_logger(__name__)


# ── Background tasks ──────────────────────────────────────────────────────────

async def _cache_reaper(interval_seconds: float = 300.0) -> None:
    """Periodically evict expired entries from the in-memory cache fallback."""
    from aim.utils.cache import get_response_cache

    while True:
        await asyncio.sleep(interval_seconds)
        cache = get_response_cache()
        removed = await cache.purge_expired_fallback()
        if removed:
            log.debug("cache.reaper_purged", removed=removed)


# ── Lifespan ──────────────────────────────────────────────────────────────────

def _assert_single_worker() -> None:
    """Crash fast if more than one worker process is detected.

    Two signals are checked:

    1. ``multiprocessing.current_process().name`` — Python's multiprocessing
       module names spawned workers "Process-N" (or "SpawnProcess-N" /
       "ForkProcess-N" on macOS/Windows).  The orchestrator is always
       "MainProcess".  Uvicorn ``--workers N`` uses multiprocessing.Process
       internally, so worker processes reliably carry these names.

    2. ``WEB_CONCURRENCY`` env var — set to the worker count by gunicorn,
       Heroku, Railway, Render, and most platform hosts that manage concurrency
       for you.  A value > 1 means multiple worker processes are expected.

    The compiled LangGraph graph and the in-process rate-limiter token buckets
    are module-level singletons.  Each OS process gets its own copy — state
    diverges silently and the rate limit becomes per-instance rather than global.
    Scale horizontally by running multiple *single-worker* instances behind a
    load balancer instead.
    """
    import multiprocessing
    import os

    proc = multiprocessing.current_process()
    is_worker = proc.name.startswith(("Process-", "SpawnProcess-", "ForkProcess-"))
    web_concurrency = int(os.environ.get("WEB_CONCURRENCY", "1"))

    if is_worker or web_concurrency > 1:
        raise RuntimeError(
            f"AIM must run with a single worker process "
            f"(detected: process={proc.name!r}, WEB_CONCURRENCY={web_concurrency}). "
            "The compiled LangGraph graph is an in-process singleton — multiple workers "
            "diverge silently. Scale by running separate single-worker instances behind "
            "a load balancer."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    _assert_single_worker()
    settings = get_settings()
    log.info("aim.startup", version=settings.app_version, env=settings.app_env)

    # Phase 13: flag deprecated MCP transports at startup so operators get
    # a structured warning before the native path is removed.
    from aim.mcp.handler import warn_if_transport_deprecated
    warn_if_transport_deprecated(settings.mcp_transport)

    # 1. OTel tracing (no-op if OTLP_ENDPOINT not set)
    from aim.utils.tracing import setup_tracing
    setup_tracing(app)

    # 2. Prometheus metadata
    init_app_info()

    # 3. Redis cache connection
    from aim.utils.cache import get_response_cache
    cache = get_response_cache()
    await cache.connect()

    # 4. Conversation store connection (shares Redis_url, separate client)
    from aim.utils.conversation_store import get_conversation_store
    conv_store = get_conversation_store()
    await conv_store.connect()

    # 5. Neo4j schema migrations (versioned, idempotent — safe on every restart)
    ingest_worker = None
    try:
        from aim.graph.migrations import run_migrations
        from aim.graph.neo4j_client import Neo4jClient

        client = Neo4jClient()
        applied = await run_migrations(client._driver, settings.neo4j_database)
        log.info("neo4j.migrations_done", applied=applied)
    except Exception as exc:
        log.warning("neo4j.migration_error", error=str(exc))

    # 6. Background ingest worker
    from aim.workers.ingest_worker import get_ingest_worker
    ingest_worker = get_ingest_worker()
    await ingest_worker.start()

    # 7. Background cache reaper
    reaper_task = asyncio.create_task(_cache_reaper(), name="cache_reaper")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    log.info("aim.shutdown_start")

    reaper_task.cancel()
    try:
        await reaper_task
    except asyncio.CancelledError:
        pass

    if ingest_worker:
        await ingest_worker.stop()

    # Close shared Neo4j driver
    try:
        from aim.graph.neo4j_client import Neo4jClient
        await Neo4jClient.shutdown()
        log.info("neo4j.driver_closed")
    except Exception as exc:
        log.warning("neo4j.shutdown_error", error=str(exc))

    # Close Redis connections
    await cache.close()
    await conv_store.close()
    log.info("aim.shutdown_complete")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Graph-backed, agentic RAG with Slack/Jira MCP context, "
            "LangGraph reasoning, Neo4j knowledge graph, and Pinecone vector search."
        ),
        # Always expose docs in non-production; set APP_ENV=production to lock down.
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── CORS ────────────────────────────────────────────────────────────────
    # Use explicitly configured origins (CORS_ORIGINS env var) if provided.
    # Falls back to wildcard in debug mode, locked-down otherwise.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.effective_cors_origins,
        allow_credentials=True if settings.cors_origins else False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["X-API-Key", "X-Request-ID", "Content-Type", "Authorization"],
        expose_headers=["X-Request-ID", "X-Data-Boundary"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(query.router,         prefix="/api/v1")
    app.include_router(graph.router,         prefix="/api/v1")
    app.include_router(conversations.router, prefix="/api/v1")
    app.include_router(feedback.router,      prefix="/api/v1")
    app.include_router(webhooks.router)
    app.include_router(mcp_sse.router)

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "aim.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_config=None,
        workers=1,  # LangGraph compiled graph is in-process; single worker required
    )
