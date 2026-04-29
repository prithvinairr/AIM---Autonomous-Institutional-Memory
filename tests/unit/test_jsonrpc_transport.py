"""Tests for JSON-RPC 2.0 MCP transport layer."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.mcp.jsonrpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcTransport,
    _error_response,
    reset_transport,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_transport()
    yield
    reset_transport()


# ── Model tests ──────────────────────────────────────────────────────────────


class TestJsonRpcModels:
    def test_request_defaults(self):
        req = JsonRpcRequest(method="initialize")
        assert req.jsonrpc == "2.0"
        assert req.params is None
        assert req.id is None

    def test_request_with_params(self):
        req = JsonRpcRequest(method="tools/call", params={"name": "slack_search"}, id=1)
        assert req.method == "tools/call"
        assert req.params == {"name": "slack_search"}
        assert req.id == 1

    def test_response_with_result(self):
        resp = JsonRpcResponse(result={"status": "ok"}, id=1)
        assert resp.result == {"status": "ok"}
        assert resp.error is None

    def test_response_with_error(self):
        resp = _error_response(PARSE_ERROR, "bad json", req_id=42)
        assert resp.error is not None
        assert resp.error.code == PARSE_ERROR
        assert resp.error.message == "bad json"
        assert resp.id == 42
        assert resp.result is None

    def test_error_response_with_data(self):
        resp = _error_response(INTERNAL_ERROR, "failed", data={"detail": "boom"})
        assert resp.error.data == {"detail": "boom"}


# ── Transport: parse errors ──────────────────────────────────────────────────


class TestTransportParseErrors:
    @pytest.mark.asyncio
    async def test_invalid_json(self):
        transport = JsonRpcTransport()
        result = await transport.handle("{not valid json")
        parsed = json.loads(result)
        assert parsed["error"]["code"] == PARSE_ERROR

    @pytest.mark.asyncio
    async def test_empty_batch(self):
        transport = JsonRpcTransport()
        result = await transport.handle("[]")
        parsed = json.loads(result)
        assert parsed["error"]["code"] == INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_non_object_request(self):
        transport = JsonRpcTransport()
        result = await transport.handle('"just a string"')
        parsed = json.loads(result)
        assert parsed["error"]["code"] == INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_wrong_jsonrpc_version(self):
        transport = JsonRpcTransport()
        req = json.dumps({"jsonrpc": "1.0", "method": "initialize", "id": 1})
        result = await transport.handle(req)
        parsed = json.loads(result)
        assert parsed["error"]["code"] == INVALID_REQUEST
        assert "2.0" in parsed["error"]["message"]

    @pytest.mark.asyncio
    async def test_missing_method(self):
        transport = JsonRpcTransport()
        req = json.dumps({"jsonrpc": "2.0", "id": 1})
        result = await transport.handle(req)
        parsed = json.loads(result)
        assert parsed["error"]["code"] == INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_invalid_params_type(self):
        transport = JsonRpcTransport()
        req = json.dumps({"jsonrpc": "2.0", "method": "initialize", "params": "string", "id": 1})
        result = await transport.handle(req)
        parsed = json.loads(result)
        assert parsed["error"]["code"] == INVALID_PARAMS


# ── Transport: method routing ────────────────────────────────────────────────


class TestTransportMethodRouting:
    @pytest.mark.asyncio
    async def test_unknown_method(self):
        transport = JsonRpcTransport()
        req = json.dumps({"jsonrpc": "2.0", "method": "unknown/method", "id": 1})
        result = await transport.handle(req)
        parsed = json.loads(result)
        assert parsed["error"]["code"] == METHOD_NOT_FOUND

    @pytest.mark.asyncio
    async def test_initialize(self):
        transport = JsonRpcTransport()

        mock_caps = []
        with patch("aim.mcp.jsonrpc.MCPHandler") as MockHandler, \
             patch("aim.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                app_name="AIM Test",
                app_version="1.0.0",
            )
            handler_inst = MockHandler.return_value
            handler_inst.list_capabilities = MagicMock(return_value=mock_caps)

            req = json.dumps({"jsonrpc": "2.0", "method": "initialize", "id": 1})
            result = await transport.handle(req)

        parsed = json.loads(result)
        assert parsed["id"] == 1
        assert parsed["error"] is None
        assert parsed["result"]["protocolVersion"] == "2024-11-05"
        assert parsed["result"]["serverInfo"]["name"] == "AIM Test"
        assert "capabilities" in parsed["result"]

    @pytest.mark.asyncio
    async def test_resources_list(self):
        from aim.schemas.mcp import MCPResource

        transport = JsonRpcTransport()
        mock_resources = [
            MCPResource(uri="slack://channel/general", name="general"),
        ]

        with patch("aim.mcp.jsonrpc.MCPHandler") as MockHandler:
            handler_inst = MockHandler.return_value
            handler_inst.list_resources = MagicMock(return_value=mock_resources)

            req = json.dumps({"jsonrpc": "2.0", "method": "resources/list", "id": 2})
            result = await transport.handle(req)

        parsed = json.loads(result)
        assert parsed["id"] == 2
        assert len(parsed["result"]["resources"]) == 1
        assert parsed["result"]["resources"][0]["uri"] == "slack://channel/general"

    @pytest.mark.asyncio
    async def test_tools_list(self):
        from aim.schemas.mcp import MCPTool

        transport = JsonRpcTransport()
        mock_tools = [
            MCPTool(name="slack_search", description="Search Slack"),
        ]

        with patch("aim.mcp.jsonrpc.MCPHandler") as MockHandler:
            handler_inst = MockHandler.return_value
            handler_inst.list_tools = MagicMock(return_value=mock_tools)

            req = json.dumps({"jsonrpc": "2.0", "method": "tools/list", "id": 3})
            result = await transport.handle(req)

        parsed = json.loads(result)
        assert parsed["id"] == 3
        assert len(parsed["result"]["tools"]) == 1
        assert parsed["result"]["tools"][0]["name"] == "slack_search"

    @pytest.mark.asyncio
    async def test_tools_call(self):
        from aim.schemas.mcp import MCPProviderType, MCPToolCallResult

        transport = JsonRpcTransport()
        mock_result = MCPToolCallResult(
            tool_name="slack_search",
            provider_type=MCPProviderType.SLACK,
            success=True,
        )

        with patch("aim.mcp.jsonrpc.MCPHandler") as MockHandler:
            handler_inst = MockHandler.return_value
            handler_inst.call_tool = AsyncMock(return_value=mock_result)

            req = json.dumps({
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "slack_search", "arguments": {"query": "test"}},
                "id": 4,
            })
            result = await transport.handle(req)

        parsed = json.loads(result)
        assert parsed["id"] == 4
        assert parsed["result"]["success"] is True
        assert parsed["result"]["tool_name"] == "slack_search"

    @pytest.mark.asyncio
    async def test_tools_call_missing_name(self):
        transport = JsonRpcTransport()

        with patch("aim.mcp.jsonrpc.MCPHandler"):
            req = json.dumps({
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"arguments": {}},
                "id": 5,
            })
            result = await transport.handle(req)

        parsed = json.loads(result)
        assert parsed["error"]["code"] == INTERNAL_ERROR
        assert "name" in parsed["error"]["data"]

    @pytest.mark.asyncio
    async def test_resources_read(self):
        from aim.schemas.mcp import MCPProviderType, MCPToolCallResult

        transport = JsonRpcTransport()
        mock_result = MCPToolCallResult(
            tool_name="read",
            provider_type=MCPProviderType.SLACK,
            success=True,
        )

        with patch("aim.mcp.jsonrpc.MCPHandler") as MockHandler:
            handler_inst = MockHandler.return_value
            handler_inst.read_resource = AsyncMock(return_value=mock_result)

            req = json.dumps({
                "jsonrpc": "2.0",
                "method": "resources/read",
                "params": {"uri": "slack://channel/general"},
                "id": 6,
            })
            result = await transport.handle(req)

        parsed = json.loads(result)
        assert parsed["id"] == 6
        assert parsed["result"]["success"] is True

    @pytest.mark.asyncio
    async def test_resources_read_missing_uri(self):
        transport = JsonRpcTransport()

        with patch("aim.mcp.jsonrpc.MCPHandler"):
            req = json.dumps({
                "jsonrpc": "2.0",
                "method": "resources/read",
                "params": {},
                "id": 7,
            })
            result = await transport.handle(req)

        parsed = json.loads(result)
        assert parsed["error"]["code"] == INTERNAL_ERROR
        assert "uri" in parsed["error"]["data"]


# ── Batch requests ───────────────────────────────────────────────────────────


class TestTransportBatch:
    @pytest.mark.asyncio
    async def test_batch_request(self):
        transport = JsonRpcTransport()
        mock_tools = []

        with patch("aim.mcp.jsonrpc.MCPHandler") as MockHandler, \
             patch("aim.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(app_name="AIM", app_version="1.0")
            handler_inst = MockHandler.return_value
            handler_inst.list_capabilities = MagicMock(return_value=[])
            handler_inst.list_tools = MagicMock(return_value=mock_tools)

            batch = json.dumps([
                {"jsonrpc": "2.0", "method": "initialize", "id": 1},
                {"jsonrpc": "2.0", "method": "tools/list", "id": 2},
            ])
            result = await transport.handle(batch)

        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["id"] == 1
        assert parsed[1]["id"] == 2


# ── Internal error handling ──────────────────────────────────────────────────


class TestTransportInternalErrors:
    @pytest.mark.asyncio
    async def test_handler_exception_returns_internal_error(self):
        transport = JsonRpcTransport()

        with patch("aim.mcp.jsonrpc.MCPHandler") as MockHandler:
            handler_inst = MockHandler.return_value
            handler_inst.list_tools = MagicMock(side_effect=RuntimeError("db down"))

            req = json.dumps({"jsonrpc": "2.0", "method": "tools/list", "id": 99})
            result = await transport.handle(req)

        parsed = json.loads(result)
        assert parsed["error"]["code"] == INTERNAL_ERROR
        assert "RuntimeError" in parsed["error"]["message"]
        assert parsed["id"] == 99

    @pytest.mark.asyncio
    async def test_tools_call_invalid_arguments_type(self):
        transport = JsonRpcTransport()

        with patch("aim.mcp.jsonrpc.MCPHandler"):
            req = json.dumps({
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "test", "arguments": "not_a_dict"},
                "id": 10,
            })
            result = await transport.handle(req)

        parsed = json.loads(result)
        assert parsed["error"]["code"] == INTERNAL_ERROR


# ── Singleton ────────────────────────────────────────────────────────────────


class TestSingleton:
    def test_get_transport_returns_same_instance(self):
        from aim.mcp.jsonrpc import get_transport
        t1 = get_transport()
        t2 = get_transport()
        assert t1 is t2

    def test_reset_transport_clears_instance(self):
        from aim.mcp.jsonrpc import get_transport, reset_transport
        t1 = get_transport()
        reset_transport()
        t2 = get_transport()
        assert t1 is not t2
