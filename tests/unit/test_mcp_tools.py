"""Tests for MCP call_tool, read_resource, and Confluence provider."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.mcp.handler import MCPHandler
from aim.schemas.mcp import (
    MCPProviderType,
    MCPResource,
    MCPServerCapabilities,
    MCPTool,
    MCPToolCallResult,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_handler_with_provider(
    provider_type: MCPProviderType = MCPProviderType.SLACK,
    tools: list[MCPTool] | None = None,
    resources: list[MCPResource] | None = None,
    fetch_result: list | None = None,
) -> tuple[MCPHandler, AsyncMock]:
    """Build an MCPHandler with one mock provider."""
    mock_provider = MagicMock()
    mock_provider.provider_type = provider_type
    caps = MCPServerCapabilities(
        provider_type=provider_type,
        provider_name=f"{provider_type.value}-test",
        version="1.0.0",
        tools=tools or [],
        resources=resources or [],
    )
    mock_provider.get_capabilities.return_value = caps
    # health_check and fetch are async
    mock_provider.health_check = AsyncMock(return_value=True)
    mock_provider.fetch = AsyncMock(return_value=fetch_result or [])

    handler = MCPHandler.__new__(MCPHandler)
    handler._providers = {provider_type: mock_provider}
    return handler, mock_provider


# ── call_tool ────────────────────────────────────────────────────────────────


class TestCallTool:
    @pytest.mark.asyncio
    async def test_calls_matching_tool(self):
        handler, mock_prov = _make_handler_with_provider(
            tools=[MCPTool(name="search_messages", description="Search Slack")],
        )
        # Mock _safe_fetch to return an empty list (valid data)
        handler._safe_fetch = AsyncMock(return_value=[])
        result = await handler.call_tool("search_messages", {"query": "auth"})
        assert isinstance(result, MCPToolCallResult)
        assert result.success is True
        assert result.tool_name == "search_messages"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        handler, _ = _make_handler_with_provider(
            tools=[MCPTool(name="existing_tool", description="exists")],
        )
        result = await handler.call_tool("nonexistent_tool", {"query": "test"})
        assert result.success is False
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_tool_exception_returns_error(self):
        handler, mock_prov = _make_handler_with_provider(
            tools=[MCPTool(name="bad_tool", description="will fail")],
        )
        # Make _safe_fetch raise
        mock_prov.fetch.side_effect = RuntimeError("Connection lost")
        # Patch _safe_fetch to raise
        handler._safe_fetch = AsyncMock(side_effect=RuntimeError("Connection lost"))
        result = await handler.call_tool("bad_tool", {"query": "test"})
        assert result.success is False
        assert "Connection lost" in result.error

    @pytest.mark.asyncio
    async def test_empty_providers_returns_unknown(self):
        handler = MCPHandler.__new__(MCPHandler)
        handler._providers = {}
        result = await handler.call_tool("any_tool", {})
        assert result.success is False


# ── read_resource ────────────────────────────────────────────────────────────


class TestReadResource:
    @pytest.mark.asyncio
    async def test_reads_matching_resource(self):
        handler, mock_prov = _make_handler_with_provider(
            resources=[MCPResource(uri="slack://channel/general", name="general")],
            fetch_result=[MagicMock(model_dump=MagicMock(return_value={"text": "hi"}))],
        )
        handler._safe_fetch = AsyncMock(return_value=[
            MagicMock(model_dump=MagicMock(return_value={"text": "hi"}))
        ])
        result = await handler.read_resource("slack://channel/general")
        assert result["uri"] == "slack://channel/general"
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_resource_not_found(self):
        handler, _ = _make_handler_with_provider(
            resources=[MCPResource(uri="slack://channel/eng", name="eng")],
        )
        result = await handler.read_resource("jira://project/SEC")
        assert "error" in result
        assert result["data"] == []


# ── Confluence provider ──────────────────────────────────────────────────────


class TestConfluenceProvider:
    @pytest.mark.asyncio
    async def test_health_check_without_credentials(self):
        from aim.mcp.confluence_provider import ConfluenceProvider

        provider = ConfluenceProvider()
        result = await provider.health_check()
        # Should return False when no credentials configured
        assert result is False

    def test_capabilities(self):
        from aim.mcp.confluence_provider import ConfluenceProvider

        provider = ConfluenceProvider()
        caps = provider.get_capabilities()
        assert caps.provider_name == "ConfluenceProvider"
        assert len(caps.tools) >= 1
        assert len(caps.resources) >= 1
        assert any("search" in t.name for t in caps.tools)

    def test_provider_type(self):
        from aim.mcp.confluence_provider import ConfluenceProvider

        provider = ConfluenceProvider()
        assert provider.provider_type == MCPProviderType.CONFLUENCE

    @pytest.mark.asyncio
    async def test_fetch_without_credentials_returns_empty(self):
        from aim.mcp.confluence_provider import ConfluenceProvider
        from aim.schemas.mcp import MCPContextRequest

        provider = ConfluenceProvider()
        request = MCPContextRequest(
            query_text="test",
            providers=[MCPProviderType.CONFLUENCE],
        )
        result = await provider.fetch(request)
        assert result == []
