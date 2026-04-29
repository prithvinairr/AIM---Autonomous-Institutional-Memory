"""Health, readiness, metrics, and circuit-breaker status endpoints."""
from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from aim.config import get_settings

log = structlog.get_logger(__name__)
router = APIRouter(tags=["ops"])


class HealthResponse(BaseModel):
    status: str
    version: str
    components: dict[str, str]


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        components={"api": "ok"},
    )


@router.get("/ready", summary="Readiness probe — checks all downstream deps")
async def ready() -> JSONResponse:
    from aim.config import get_settings
    from aim.graph.neo4j_client import Neo4jClient
    from aim.vectordb.factory import get_vectordb_provider
    from aim.mcp.handler import MCPHandler
    from aim.utils.cache import get_response_cache
    from aim.workers.ingest_worker import get_ingest_worker

    settings = get_settings()
    vector_provider_name = (settings.vector_db_provider or "pinecone").lower()
    neo4j = Neo4jClient()
    vector = get_vectordb_provider()
    mcp = MCPHandler()
    cache = get_response_cache()
    worker = get_ingest_worker()

    neo4j_ok, vector_ok, mcp_results, cache_ok = await asyncio.gather(
        neo4j.health_check(),
        vector.health_check(),
        mcp.health_check(),
        cache.health_check(),
        return_exceptions=True,
    )

    def _status(result: Any, name: str) -> str:
        """Distinguish healthy / unhealthy / exception for each component."""
        if isinstance(result, BaseException):
            log.warning("readiness.check_exception", component=name, error=str(result))
            return f"error ({type(result).__name__})"
        return "ok" if result is True else "degraded"

    components: dict[str, Any] = {
        "neo4j": _status(neo4j_ok, "neo4j"),
        vector_provider_name: _status(vector_ok, vector_provider_name),
        "cache": (
            f"ok ({cache.backend()})"
            if cache_ok is True
            else _status(cache_ok, "cache") if isinstance(cache_ok, BaseException)
            else "degraded (memory fallback)"
        ),
        "ingest_worker": "ok" if worker.is_alive else "degraded (worker stopped)",
    }
    if isinstance(mcp_results, dict):
        for provider, ok in mcp_results.items():
            components[f"mcp_{provider}"] = "ok" if ok else "degraded"
    elif isinstance(mcp_results, BaseException):
        log.warning("readiness.mcp_exception", error=str(mcp_results))
        components["mcp"] = f"error ({type(mcp_results).__name__})"

    has_errors = any(v.startswith("error") for v in components.values())
    all_ok = all(v.startswith("ok") for v in components.values())
    overall = "ok" if all_ok else ("error" if has_errors else "degraded")
    http_status = (
        status.HTTP_200_OK if overall == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(
        status_code=http_status,
        content={"status": overall, "components": components},
    )


@router.get("/metrics", summary="Prometheus metrics scrape endpoint")
async def metrics() -> Response:
    from aim.utils.metrics import prometheus_response, update_circuit_metrics

    update_circuit_metrics()
    body, content_type = prometheus_response()
    return Response(content=body, media_type=content_type)


@router.get("/circuits", summary="Circuit breaker status for all services")
async def circuit_status() -> JSONResponse:
    from aim.utils.circuit_breaker import all_statuses

    return JSONResponse(content={"circuits": all_statuses()})


@router.get("/mcp/capabilities", summary="MCP provider capability discovery")
async def mcp_capabilities() -> JSONResponse:
    """Returns declared capabilities for all registered MCP providers.

    Aligned with MCP spec ``initialize`` response — lists available
    resources (data sources) and tools (actions) per provider.
    """
    from aim.mcp.handler import MCPHandler

    handler = MCPHandler()
    caps = handler.list_capabilities()
    return JSONResponse(content={
        "capabilities": [c.model_dump(mode="json") for c in caps],
        "total_resources": sum(len(c.resources) for c in caps),
        "total_tools": sum(len(c.tools) for c in caps),
    })


@router.get("/mcp/resources", summary="MCP resources/list")
async def mcp_resources() -> JSONResponse:
    """List all resources across all providers (MCP spec: resources/list)."""
    from aim.mcp.handler import MCPHandler

    handler = MCPHandler()
    resources = handler.list_resources()
    return JSONResponse(content={
        "resources": [r.model_dump(mode="json") for r in resources],
    })


@router.get("/mcp/tools", summary="MCP tools/list")
async def mcp_tools() -> JSONResponse:
    """List all tools across all providers (MCP spec: tools/list)."""
    from aim.mcp.handler import MCPHandler

    handler = MCPHandler()
    tools = handler.list_tools()
    return JSONResponse(content={
        "tools": [t.model_dump(mode="json") for t in tools],
    })


class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = {}


@router.post("/mcp/tools/call", summary="MCP tools/call")
async def mcp_tool_call(request: ToolCallRequest) -> JSONResponse:
    """Invoke a declared MCP tool by name (MCP spec: tools/call)."""
    from aim.mcp.handler import MCPHandler

    handler = MCPHandler()
    result = await handler.call_tool(request.tool_name, request.arguments)
    return JSONResponse(
        content=result.model_dump(mode="json"),
        status_code=200 if result.success else 404,
    )


@router.post("/mcp/jsonrpc", summary="JSON-RPC 2.0 MCP transport")
async def mcp_jsonrpc(req: Request) -> Response:
    """Full MCP spec JSON-RPC 2.0 transport endpoint.

    Accepts a JSON-RPC 2.0 request (or batch array) and returns the
    corresponding response. Supports: ``initialize``, ``resources/list``,
    ``tools/list``, ``tools/call``, ``resources/read``.

    Enabled when ``MCP_TRANSPORT=jsonrpc`` (default: ``native``).
    """
    settings = get_settings()
    if settings.mcp_transport != "jsonrpc":
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "JSON-RPC transport is not enabled. Set MCP_TRANSPORT=jsonrpc."},
        )

    from aim.mcp.jsonrpc import get_transport

    raw_body = (await req.body()).decode("utf-8")
    transport = get_transport()
    result = await transport.handle(raw_body)
    return Response(
        content=result,
        media_type="application/json",
    )
