"""Integration tests for health, readiness, metrics and circuit endpoints.

Note on patch targets: health.py imports Neo4jClient, PineconeClient etc.
*inside* the ready() function body (lazy imports). Therefore patches must
target the source module namespace, not aim.api.routes.health.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


# ── /health ───────────────────────────────────────────────────────────────────

async def test_health_returns_200(client):
    response = await client.get("/health")
    assert response.status_code == 200


async def test_health_response_contains_required_fields(client):
    data = (await client.get("/health")).json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["components"]["api"] == "ok"


# ── /ready ────────────────────────────────────────────────────────────────────

def _ready_patches(neo4j_ok=True, pinecone_ok=True, mcp_ok=True, cache_ok=True, backend="redis", worker_alive=True):
    """Return a context manager stack that mocks all /ready dependencies."""
    from contextlib import ExitStack

    stack = ExitStack()

    MockNeo4j = stack.enter_context(patch("aim.graph.neo4j_client.Neo4jClient"))
    MockNeo4j.return_value.health_check = AsyncMock(return_value=neo4j_ok)

    MockPinecone = stack.enter_context(patch("aim.vectordb.pinecone_client.PineconeClient"))
    MockPinecone.return_value.health_check = AsyncMock(return_value=pinecone_ok)

    MockMCP = stack.enter_context(patch("aim.mcp.handler.MCPHandler"))
    MockMCP.return_value.health_check = AsyncMock(
        return_value={"slack": mcp_ok, "jira": mcp_ok}
    )

    mock_cache_inst = MagicMock()
    mock_cache_inst.health_check = AsyncMock(return_value=cache_ok)
    mock_cache_inst.backend = MagicMock(return_value=backend)
    MockCache = stack.enter_context(patch("aim.utils.cache.get_response_cache"))
    MockCache.return_value = mock_cache_inst

    mock_worker = MagicMock()
    mock_worker.is_alive = worker_alive
    MockWorker = stack.enter_context(patch("aim.workers.ingest_worker.get_ingest_worker"))
    MockWorker.return_value = mock_worker

    return stack


async def test_ready_returns_200_when_all_deps_healthy(client):
    with _ready_patches():
        response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_ready_returns_503_when_neo4j_is_down(client):
    with _ready_patches(neo4j_ok=False):
        response = await client.get("/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["components"]["neo4j"] == "degraded"


async def test_ready_returns_503_when_pinecone_is_down(client):
    with _ready_patches(pinecone_ok=False):
        response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["components"]["pinecone"] == "degraded"


async def test_ready_shows_memory_fallback_in_cache_component(client):
    with _ready_patches(cache_ok=False, backend="memory"):
        response = await client.get("/ready")
    data = response.json()
    assert "memory" in data["components"]["cache"]


async def test_ready_shows_redis_when_cache_healthy(client):
    with _ready_patches(backend="redis"):
        response = await client.get("/ready")
    assert "redis" in response.json()["components"]["cache"]


async def test_ready_handles_neo4j_exception(client):
    """When a health check raises an exception, /ready reports error with type name."""
    from contextlib import ExitStack

    stack = ExitStack()

    MockNeo4j = stack.enter_context(patch("aim.graph.neo4j_client.Neo4jClient"))
    MockNeo4j.return_value.health_check = AsyncMock(side_effect=ConnectionError("boom"))

    MockPinecone = stack.enter_context(patch("aim.vectordb.pinecone_client.PineconeClient"))
    MockPinecone.return_value.health_check = AsyncMock(return_value=True)

    MockMCP = stack.enter_context(patch("aim.mcp.handler.MCPHandler"))
    MockMCP.return_value.health_check = AsyncMock(return_value={"slack": True, "jira": True})

    mock_cache_inst = MagicMock()
    mock_cache_inst.health_check = AsyncMock(return_value=True)
    mock_cache_inst.backend = MagicMock(return_value="redis")
    MockCache = stack.enter_context(patch("aim.utils.cache.get_response_cache"))
    MockCache.return_value = mock_cache_inst

    mock_worker = MagicMock()
    mock_worker.is_alive = True
    MockWorker = stack.enter_context(patch("aim.workers.ingest_worker.get_ingest_worker"))
    MockWorker.return_value = mock_worker

    with stack:
        response = await client.get("/ready")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "error"
    assert "ConnectionError" in data["components"]["neo4j"]


async def test_ready_handles_mcp_exception(client):
    """When MCP health check raises, /ready reports the mcp error."""
    from contextlib import ExitStack

    stack = ExitStack()

    MockNeo4j = stack.enter_context(patch("aim.graph.neo4j_client.Neo4jClient"))
    MockNeo4j.return_value.health_check = AsyncMock(return_value=True)

    MockPinecone = stack.enter_context(patch("aim.vectordb.pinecone_client.PineconeClient"))
    MockPinecone.return_value.health_check = AsyncMock(return_value=True)

    MockMCP = stack.enter_context(patch("aim.mcp.handler.MCPHandler"))
    MockMCP.return_value.health_check = AsyncMock(side_effect=TimeoutError("mcp down"))

    mock_cache_inst = MagicMock()
    mock_cache_inst.health_check = AsyncMock(return_value=True)
    mock_cache_inst.backend = MagicMock(return_value="redis")
    MockCache = stack.enter_context(patch("aim.utils.cache.get_response_cache"))
    MockCache.return_value = mock_cache_inst

    mock_worker = MagicMock()
    mock_worker.is_alive = True
    MockWorker = stack.enter_context(patch("aim.workers.ingest_worker.get_ingest_worker"))
    MockWorker.return_value = mock_worker

    with stack:
        response = await client.get("/ready")

    data = response.json()
    assert response.status_code == 503
    assert "TimeoutError" in data["components"].get("mcp", "")


# ── /metrics ──────────────────────────────────────────────────────────────────

async def test_metrics_endpoint_returns_200(client):
    with (
        patch("aim.utils.metrics.update_circuit_metrics"),
        patch(
            "aim.utils.metrics.prometheus_response",
            return_value=(b"# HELP aim_queries_total\n", "text/plain; version=0.0.4"),
        ),
    ):
        response = await client.get("/metrics")
    assert response.status_code == 200


# ── /circuits ─────────────────────────────────────────────────────────────────

async def test_circuits_returns_list(client):
    response = await client.get("/circuits")
    assert response.status_code == 200
    data = response.json()
    assert "circuits" in data
    assert isinstance(data["circuits"], list)


async def test_circuits_shows_registered_breaker(client):
    from aim.utils.circuit_breaker import get_breaker

    # Register a breaker so the registry is non-empty
    get_breaker("test_svc")

    response = await client.get("/circuits")
    names = [c["name"] for c in response.json()["circuits"]]
    assert "test_svc" in names


# ── /mcp/* ───────────────────────────────────────────────────────────────────


async def test_mcp_capabilities_returns_200(client):
    with patch("aim.mcp.handler.MCPHandler") as MockHandler:
        MockHandler.return_value.list_capabilities.return_value = []
        response = await client.get("/mcp/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "capabilities" in data
    assert data["total_resources"] == 0
    assert data["total_tools"] == 0


async def test_mcp_resources_returns_200(client):
    with patch("aim.mcp.handler.MCPHandler") as MockHandler:
        MockHandler.return_value.list_resources.return_value = []
        response = await client.get("/mcp/resources")
    assert response.status_code == 200
    assert "resources" in response.json()


async def test_mcp_tools_returns_200(client):
    with patch("aim.mcp.handler.MCPHandler") as MockHandler:
        MockHandler.return_value.list_tools.return_value = []
        response = await client.get("/mcp/tools")
    assert response.status_code == 200
    assert "tools" in response.json()


async def test_mcp_tool_call_success(client):
    from aim.schemas.mcp import MCPProviderType, MCPToolCallResult

    mock_result = MCPToolCallResult(
        tool_name="search_messages",
        provider_type=MCPProviderType.SLACK,
        success=True,
        data=[],
    )
    with patch("aim.mcp.handler.MCPHandler") as MockHandler:
        MockHandler.return_value.call_tool = AsyncMock(return_value=mock_result)
        response = await client.post("/mcp/tools/call", json={
            "tool_name": "search_messages",
            "arguments": {"query": "test"},
        })
    assert response.status_code == 200
    assert response.json()["success"] is True


async def test_mcp_tool_call_unknown_returns_404(client):
    from aim.schemas.mcp import MCPProviderType, MCPToolCallResult

    mock_result = MCPToolCallResult(
        tool_name="nonexistent",
        provider_type=MCPProviderType.SLACK,
        success=False,
        error="Unknown tool",
        data=[],
    )
    with patch("aim.mcp.handler.MCPHandler") as MockHandler:
        MockHandler.return_value.call_tool = AsyncMock(return_value=mock_result)
        response = await client.post("/mcp/tools/call", json={
            "tool_name": "nonexistent",
            "arguments": {},
        })
    assert response.status_code == 404
