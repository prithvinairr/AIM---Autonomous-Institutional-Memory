"""JSON-RPC 2.0 transport layer for MCP (Model Context Protocol).

Implements the JSON-RPC 2.0 envelope around the existing MCPHandler methods,
enabling spec-compliant MCP communication. Supported methods:

  - ``initialize``       — server capabilities handshake
  - ``resources/list``   — enumerate available resources
  - ``tools/list``       — enumerate available tools
  - ``tools/call``       — invoke a named tool
  - ``resources/read``   — read a resource by URI

Error codes follow both JSON-RPC 2.0 and MCP spec conventions:
  -32700  Parse error
  -32600  Invalid request
  -32601  Method not found
  -32602  Invalid params
  -32603  Internal error

Usage:
  transport = JsonRpcTransport()
  response = await transport.handle(raw_json_string)
"""
from __future__ import annotations

import json
import time
from typing import Any

import structlog
from pydantic import BaseModel, Field

from aim.mcp.handler import MCPHandler
from aim.utils.metrics import MCP_FETCH_LATENCY

log = structlog.get_logger(__name__)


# ── JSON-RPC 2.0 Models ─────────────────────────────────────────────────────


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error object."""
    code: int
    message: str
    data: Any | None = None


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request envelope."""
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] | None = None
    id: int | str | None = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response envelope."""
    jsonrpc: str = "2.0"
    result: Any | None = None
    error: JsonRpcError | None = None
    id: int | str | None = None


# ── Standard Error Codes ─────────────────────────────────────────────────────

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _error_response(
    code: int,
    message: str,
    req_id: int | str | None = None,
    data: Any | None = None,
) -> JsonRpcResponse:
    """Build a JSON-RPC error response."""
    return JsonRpcResponse(
        id=req_id,
        error=JsonRpcError(code=code, message=message, data=data),
    )


# ── Transport ────────────────────────────────────────────────────────────────


class JsonRpcTransport:
    """Routes JSON-RPC 2.0 requests to MCPHandler methods.

    Stateless — each ``handle()`` call creates a fresh MCPHandler.
    Thread-safe for concurrent use in async contexts.
    """

    # Method name → handler coroutine mapping (set up in _dispatch)
    _METHODS = frozenset({
        "initialize",
        "notifications/initialized",
        "resources/list",
        "tools/list",
        "tools/call",
        "resources/read",
        "ping",
        "prompts/list",
        "prompts/get",
        "resources/subscribe",
        "resources/unsubscribe",
    })

    async def handle(self, raw: str) -> str:
        """Parse a JSON-RPC request string, dispatch, and return JSON response.

        Always returns valid JSON — never raises.
        """
        # 1. Parse JSON
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            resp = _error_response(PARSE_ERROR, f"Parse error: {exc}")
            return resp.model_dump_json()

        # 2. Handle batch requests
        if isinstance(data, list):
            if not data:
                resp = _error_response(INVALID_REQUEST, "Empty batch")
                return resp.model_dump_json()
            results = []
            for item in data:
                result = await self._handle_single(item)
                if result is not None:  # notifications have no response
                    results.append(result)
            # Return array of responses
            return json.dumps([json.loads(r.model_dump_json()) for r in results])

        # 3. Single request
        resp = await self._handle_single(data)
        if resp is None:
            return ""  # notification — no response
        return resp.model_dump_json()

    async def _handle_single(self, data: Any) -> JsonRpcResponse | None:
        """Dispatch a single parsed JSON-RPC request."""
        # Validate structure
        if not isinstance(data, dict):
            return _error_response(INVALID_REQUEST, "Request must be a JSON object")

        jsonrpc = data.get("jsonrpc")
        if jsonrpc != "2.0":
            return _error_response(
                INVALID_REQUEST,
                f"Invalid jsonrpc version: {jsonrpc!r} (must be '2.0')",
                req_id=data.get("id"),
            )

        method = data.get("method")
        if not isinstance(method, str):
            return _error_response(
                INVALID_REQUEST,
                "Missing or invalid 'method' field",
                req_id=data.get("id"),
            )

        req_id = data.get("id")
        params = data.get("params", {}) or {}

        if not isinstance(params, dict):
            return _error_response(
                INVALID_PARAMS,
                "Params must be a JSON object",
                req_id=req_id,
            )

        # Parse into model for validation
        request = JsonRpcRequest(
            jsonrpc="2.0",
            method=method,
            params=params,
            id=req_id,
        )

        # Check method exists
        if request.method not in self._METHODS:
            return _error_response(
                METHOD_NOT_FOUND,
                f"Unknown method: {request.method}",
                req_id=req_id,
            )

        # Dispatch
        t0 = time.perf_counter()
        try:
            result = await self._dispatch(request)
            log.debug(
                "jsonrpc.success",
                method=request.method,
                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            )
            return JsonRpcResponse(id=req_id, result=result)
        except Exception as exc:
            log.error(
                "jsonrpc.internal_error",
                method=request.method,
                error=str(exc),
            )
            return _error_response(
                INTERNAL_ERROR,
                f"Internal error: {type(exc).__name__}",
                req_id=req_id,
                data=str(exc),
            )

    async def _dispatch(self, request: JsonRpcRequest) -> Any:
        """Route a validated request to the appropriate MCPHandler method."""
        handler = MCPHandler()
        params = request.params or {}

        if request.method == "initialize":
            return await self._handle_initialize(handler, params)
        elif request.method == "notifications/initialized":
            # MCP spec: client acknowledges initialization — no-op response
            log.debug("jsonrpc.notifications.initialized")
            return {}
        elif request.method == "resources/list":
            return await self._handle_resources_list(handler)
        elif request.method == "tools/list":
            return await self._handle_tools_list(handler)
        elif request.method == "tools/call":
            return await self._handle_tools_call(handler, params)
        elif request.method == "resources/read":
            return await self._handle_resources_read(handler, params)
        elif request.method == "ping":
            # MCP spec: ping is a no-op keepalive — return empty result
            return {}
        elif request.method == "prompts/list":
            return await self._handle_prompts_list(handler)
        elif request.method == "prompts/get":
            return await self._handle_prompts_get(handler, params)
        elif request.method in ("resources/subscribe", "resources/unsubscribe"):
            # Acknowledge subscription requests — this server is stateless so
            # we log and return empty (notifications would require a live client connection)
            log.debug("jsonrpc.subscription", method=request.method, uri=params.get("uri", ""))
            return {}
        else:
            raise ValueError(f"Unhandled method: {request.method}")

    # ── Method handlers ──────────────────────────────────────────────────────

    async def _handle_initialize(
        self,
        handler: MCPHandler,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """MCP initialize handshake — return server info + capabilities."""
        from aim.config import get_settings
        settings = get_settings()

        caps = handler.list_capabilities()
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": settings.app_name,
                "version": settings.app_version,
            },
            "capabilities": {
                "resources": {"listChanged": False, "subscribe": True},
                "tools": {"listChanged": False},
                "prompts": {},
                "experimental": {"ping": True},
            },
            "providers": [
                c.model_dump(mode="json") for c in caps
            ],
        }

    async def _handle_resources_list(
        self,
        handler: MCPHandler,
    ) -> dict[str, Any]:
        """MCP resources/list — enumerate all available resources."""
        resources = handler.list_resources()
        return {
            "resources": [r.model_dump(mode="json") for r in resources],
        }

    async def _handle_tools_list(
        self,
        handler: MCPHandler,
    ) -> dict[str, Any]:
        """MCP tools/list — enumerate all available tools."""
        tools = handler.list_tools()
        return {
            "tools": [t.model_dump(mode="json") for t in tools],
        }

    async def _handle_tools_call(
        self,
        handler: MCPHandler,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """MCP tools/call — invoke a tool by name."""
        tool_name = params.get("name")
        if not tool_name:
            raise ValueError("Missing required parameter: 'name'")

        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError("'arguments' must be a JSON object")

        result = await handler.call_tool(tool_name, arguments)
        return result.model_dump(mode="json")

    async def _handle_resources_read(
        self,
        handler: MCPHandler,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """MCP resources/read — read a resource by URI."""
        uri = params.get("uri")
        if not uri:
            raise ValueError("Missing required parameter: 'uri'")

        result = await handler.read_resource(uri)
        return result.model_dump(mode="json")

    async def _handle_prompts_list(self, handler: MCPHandler) -> dict[str, Any]:
        """MCP prompts/list — return available prompt templates."""
        handler.list_capabilities()
        # Return empty list since this server's prompts come from upstream providers
        return {"prompts": []}

    async def _handle_prompts_get(
        self,
        handler: MCPHandler,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """MCP prompts/get — retrieve a named prompt template."""
        name = params.get("name", "")
        if not name:
            raise ValueError("Missing required param: name")
        # This server doesn't expose local prompts — raise not-found
        raise ValueError(f"Prompt not found: {name}")


# ── Singleton ────────────────────────────────────────────────────────────────

_transport_instance: JsonRpcTransport | None = None


def get_transport() -> JsonRpcTransport:
    """Return the cached transport singleton."""
    global _transport_instance
    if _transport_instance is None:
        _transport_instance = JsonRpcTransport()
    return _transport_instance


def reset_transport() -> None:
    """Reset the singleton (for testing)."""
    global _transport_instance
    _transport_instance = None
