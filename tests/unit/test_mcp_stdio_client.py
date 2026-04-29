"""Tests for MCP stdio client, registry, and session."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.mcp.client.stdio_client import MCPRemoteError, StdioMCPClient
from aim.mcp.client.registry import MCPServerSpec, get_server_spec, register_server
from aim.mcp.client.session import MCPClientSession, MCPSessionPool
from aim.schemas.mcp import MCPProviderType


# ── StdioMCPClient ───────────────────────────────────────────────────────────

class TestStdioMCPClient:
    def test_init(self):
        client = StdioMCPClient(command="echo", args=["hello"])
        assert client._command == "echo"
        assert client._args == ["hello"]
        assert not client.alive

    @pytest.mark.asyncio
    async def test_send_raises_when_not_started(self):
        client = StdioMCPClient(command="echo")
        with pytest.raises(RuntimeError, match="not running"):
            await client.send("test/method")

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        client = StdioMCPClient(command="echo")
        await client.stop()  # Should not raise

    def test_alive_false_when_not_started(self):
        client = StdioMCPClient(command="echo")
        assert client.alive is False


# ── MCPRemoteError ───────────────────────────────────────────────────────────

class TestMCPRemoteError:
    def test_error_attributes(self):
        err = MCPRemoteError(code=-32600, message="Invalid Request")
        assert err.code == -32600
        assert err.message == "Invalid Request"
        assert "-32600" in str(err)
        assert "Invalid Request" in str(err)


# ── Registry ─────────────────────────────────────────────────────────────────

class TestRegistry:
    def test_default_slack_spec(self):
        spec = get_server_spec(MCPProviderType.SLACK)
        assert spec is not None
        assert spec.command == "npx"
        assert "@modelcontextprotocol/server-slack" in spec.args[1]

    def test_default_jira_spec(self):
        spec = get_server_spec(MCPProviderType.JIRA)
        assert spec is not None
        assert spec.command == "uvx"

    def test_register_custom_server(self):
        custom_spec = MCPServerSpec(
            command="python",
            args=["-m", "my_mcp_server"],
            env_keys=["MY_TOKEN"],
        )
        register_server(MCPProviderType.SLACK, custom_spec)
        retrieved = get_server_spec(MCPProviderType.SLACK)
        assert retrieved is not None
        assert retrieved.command == "python"

        # Restore default
        from aim.mcp.client.registry import _DEFAULT_REGISTRY
        _DEFAULT_REGISTRY[MCPProviderType.SLACK] = MCPServerSpec(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-slack"],
            env_keys=["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"],
        )

    def test_build_env_from_settings(self):
        spec = MCPServerSpec(
            command="test",
            env_keys=["SLACK_BOT_TOKEN"],
        )
        mock_settings = MagicMock()
        mock_settings.slack_bot_token = "xoxb-test"
        env = spec.build_env(mock_settings)
        assert env["SLACK_BOT_TOKEN"] == "xoxb-test"

    def test_build_env_missing_key(self):
        spec = MCPServerSpec(
            command="test",
            env_keys=["NONEXISTENT_KEY"],
        )
        mock_settings = MagicMock(spec=[])
        mock_settings.nonexistent_key = None
        # Should not raise, just skip
        env = spec.build_env(mock_settings)
        # Key not in env unless in os.environ
        # (might be there from CI, so just check it doesn't raise)
        assert isinstance(env, dict)


# ── MCPClientSession ─────────────────────────────────────────────────────────

class TestMCPClientSession:
    def test_init(self):
        session = MCPClientSession(MCPProviderType.SLACK)
        assert session.provider_type == MCPProviderType.SLACK
        assert not session.alive

    @pytest.mark.asyncio
    async def test_start_without_spec_raises(self):
        # Use a provider type that might not have a spec
        session = MCPClientSession(MCPProviderType.CONFLUENCE)
        # Confluence has a spec in registry, so let's mock the registry
        with patch("aim.mcp.client.session.get_server_spec", return_value=None):
            with pytest.raises(ValueError, match="No MCP server spec"):
                await session.start()

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        session = MCPClientSession(MCPProviderType.SLACK)
        await session.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_list_tools_when_not_alive(self):
        session = MCPClientSession(MCPProviderType.SLACK)
        tools = await session.list_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_list_resources_when_not_alive(self):
        session = MCPClientSession(MCPProviderType.SLACK)
        resources = await session.list_resources()
        assert resources == []

    @pytest.mark.asyncio
    async def test_call_tool_when_not_alive(self):
        session = MCPClientSession(MCPProviderType.SLACK)
        with pytest.raises(RuntimeError, match="not running"):
            await session.call_tool("test_tool")

    @pytest.mark.asyncio
    async def test_read_resource_when_not_alive(self):
        session = MCPClientSession(MCPProviderType.SLACK)
        with pytest.raises(RuntimeError, match="not running"):
            await session.read_resource("slack://channel/general")


# ── MCPSessionPool ───────────────────────────────────────────────────────────

class TestMCPSessionPool:
    @pytest.mark.asyncio
    async def test_shutdown_empty(self):
        pool = MCPSessionPool()
        await pool.shutdown()  # Should not raise

    def test_health_empty(self):
        pool = MCPSessionPool()
        assert pool.health() == {}

    @pytest.mark.asyncio
    async def test_get_session_creates_new(self):
        pool = MCPSessionPool()
        mock_session = MagicMock(spec=MCPClientSession)
        mock_session.alive = True
        mock_session.start = AsyncMock()

        with patch("aim.mcp.client.session.MCPClientSession", return_value=mock_session):
            session = await pool.get_session(MCPProviderType.SLACK)

        assert session is mock_session
        mock_session.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_session_reuses_alive(self):
        pool = MCPSessionPool()
        mock_session = MagicMock(spec=MCPClientSession)
        mock_session.alive = True
        pool._sessions[MCPProviderType.SLACK] = mock_session

        session = await pool.get_session(MCPProviderType.SLACK)
        assert session is mock_session


# ── Singleton helpers ────────────────────────────────────────────────────────

def test_get_session_pool_singleton():
    from aim.mcp.client.session import get_session_pool, reset_session_pool
    reset_session_pool()
    pool1 = get_session_pool()
    pool2 = get_session_pool()
    assert pool1 is pool2
    reset_session_pool()
