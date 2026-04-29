"""Shared pytest fixtures for the AIM test suite.

Design principles:
  - All external services (Neo4j, Pinecone, Redis, Anthropic, OpenAI, MCP)
    are mocked — no real credentials or network calls are needed to run tests.
  - Module-level singletons are reset between every test to prevent
    cross-test state leakage.
  - Integration tests use a no-op lifespan so startup I/O is skipped.
  - The default test client sets X-API-Key to TEST_API_KEY, which matches
    the API_KEYS env var injected by the ``env_vars`` fixture.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

TEST_API_KEY = "test-key-abcdefgh"


# ── Singleton reset (runs after every test) ───────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_singletons():
    """Tear down all module-level singletons so tests are fully isolated."""
    yield

    from aim.config import get_settings
    get_settings.cache_clear()

    import aim.utils.cache as _cache_mod
    _cache_mod._cache_instance = None

    import aim.utils.circuit_breaker as _cb_mod
    _cb_mod._registry.clear()

    import aim.graph.neo4j_client as _neo4j_mod
    _neo4j_mod._driver_instance = None

    import aim.vectordb.pinecone_client as _pc_mod
    _pc_mod._embed_cache_initialized = False
    _pc_mod._embed_lock = None          # was incorrectly named _embed_cache_lock
    _pc_mod._pinecone_index = None
    _pc_mod._pinecone_init_lock = None
    _pc_mod._pending_embeds.clear()

    import aim.workers.ingest_worker as _worker_mod
    _worker_mod._worker_instance = None

    import aim.mcp.handler as _mcp_mod
    _mcp_mod.MCPHandler.reset_registry()

    import aim.api.deps as _deps_mod
    _deps_mod._buckets.clear()

    import aim.utils.conversation_store as _conv_mod
    _conv_mod._store_instance = None

    # New singletons added in Phase 1-3
    import aim.utils.sovereignty as _sov_mod
    _sov_mod._guard = None

    import aim.utils.data_classification as _dc_mod
    _dc_mod._classifier = None

    import aim.llm.factory as _llm_mod
    _llm_mod._llm_instance = None
    _llm_mod._embedding_instance = None

    import aim.vectordb.factory as _vdb_mod
    _vdb_mod._vectordb_instance = None

    import aim.mcp.client.session as _mcp_session_mod
    _mcp_session_mod._pool = None

    import aim.workers.mcp_ingest_worker as _ingest_mod
    _ingest_mod._worker = None


# ── Environment / settings ────────────────────────────────────────────────────

@pytest.fixture
def env_vars(monkeypatch):
    """Inject safe test credentials into the environment and reload settings."""
    _vars = {
        "APP_ENV": "development",
        "DEBUG": "true",
        # pydantic-settings expects list[str] fields as JSON arrays
        "API_KEYS": f'["{TEST_API_KEY}"]',
        "ANTHROPIC_API_KEY": "test-anthropic-key",
        "NEO4J_PASSWORD": "test-password",
        "PINECONE_API_KEY": "pcsk-test-key-00000000",
        "OPENAI_API_KEY": "sk-openai-test-000000",
        "JIRA_API_TOKEN": "test-jira-token",
        "JIRA_BASE_URL": "https://test.atlassian.net",
        "SLACK_BOT_TOKEN": "xoxb-test-token",
        "REDIS_URL": "redis://invalid-test-host:6379",
    }
    for k, v in _vars.items():
        monkeypatch.setenv(k, v)

    from aim.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── FastAPI integration fixtures ──────────────────────────────────────────────

@pytest.fixture
def test_app(env_vars):
    """FastAPI app with a no-op lifespan — no external connections on startup."""

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    with patch("aim.main.lifespan", _noop_lifespan):
        from aim.main import create_app
        return create_app()


@pytest.fixture
async def client(test_app):
    """Async HTTP test client with the test API key pre-set."""
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"X-API-Key": TEST_API_KEY},
    ) as c:
        yield c
