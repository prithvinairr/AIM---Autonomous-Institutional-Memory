"""Tests for MCP spec-aligned capability discovery."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from aim.mcp.handler import MCPHandler
from aim.schemas.mcp import (
    MCPProviderType,
    MCPResource,
    MCPServerCapabilities,
    MCPTool,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    MCPHandler.reset_registry()
    yield
    MCPHandler.reset_registry()


def _mock_settings():
    s = MagicMock()
    s.slack_bot_token = ""
    s.slack_app_token = ""
    s.slack_default_channels = ["general", "engineering"]
    s.jira_base_url = "https://test.atlassian.net"
    s.jira_email = ""
    s.jira_api_token = ""
    s.jira_default_projects = ["ENG", "ML"]
    s.mcp_handler_timeout_seconds = 25.0
    s.mcp_provider_timeout_seconds = 15.0
    return s


def test_list_capabilities_returns_all_providers():
    with patch("aim.mcp.slack_provider.get_settings", return_value=_mock_settings()), \
         patch("aim.mcp.jira_provider.get_settings", return_value=_mock_settings()):
        handler = MCPHandler()
        caps = handler.list_capabilities()

    assert len(caps) == 2
    types = {c.provider_type for c in caps}
    assert MCPProviderType.SLACK in types
    assert MCPProviderType.JIRA in types


def test_slack_capabilities_list_channels():
    with patch("aim.mcp.slack_provider.get_settings", return_value=_mock_settings()), \
         patch("aim.mcp.jira_provider.get_settings", return_value=_mock_settings()):
        handler = MCPHandler()
        caps = handler.list_capabilities()

    slack_cap = next(c for c in caps if c.provider_type == MCPProviderType.SLACK)
    assert len(slack_cap.resources) == 2
    assert any("general" in r.uri for r in slack_cap.resources)
    assert len(slack_cap.tools) == 1
    assert slack_cap.tools[0].name == "slack_search"


def test_jira_capabilities_list_projects():
    with patch("aim.mcp.slack_provider.get_settings", return_value=_mock_settings()), \
         patch("aim.mcp.jira_provider.get_settings", return_value=_mock_settings()):
        handler = MCPHandler()
        caps = handler.list_capabilities()

    jira_cap = next(c for c in caps if c.provider_type == MCPProviderType.JIRA)
    assert len(jira_cap.resources) == 2
    assert any("ENG" in r.name for r in jira_cap.resources)
    assert len(jira_cap.tools) == 1
    assert jira_cap.tools[0].name == "jira_search"
    assert "query" in jira_cap.tools[0].input_schema["properties"]


def test_list_resources_aggregates_across_providers():
    with patch("aim.mcp.slack_provider.get_settings", return_value=_mock_settings()), \
         patch("aim.mcp.jira_provider.get_settings", return_value=_mock_settings()):
        handler = MCPHandler()
        resources = handler.list_resources()

    # 2 slack channels + 2 jira projects = 4 resources
    assert len(resources) == 4
    uris = [r.uri for r in resources]
    assert any("slack://" in u for u in uris)
    assert any("jira://" in u for u in uris)


def test_list_tools_aggregates_across_providers():
    with patch("aim.mcp.slack_provider.get_settings", return_value=_mock_settings()), \
         patch("aim.mcp.jira_provider.get_settings", return_value=_mock_settings()):
        handler = MCPHandler()
        tools = handler.list_tools()

    assert len(tools) == 2
    names = {t.name for t in tools}
    assert "slack_search" in names
    assert "jira_search" in names


def test_custom_provider_capabilities():
    """Custom providers that implement get_capabilities are discovered."""

    class CustomProvider:
        provider_type = MCPProviderType.SLACK

        def get_capabilities(self):
            return MCPServerCapabilities(
                provider_type=MCPProviderType.SLACK,
                provider_name="CustomSlack",
                resources=[
                    MCPResource(uri="slack://custom", name="custom", description="Custom"),
                ],
                tools=[],
            )

        async def fetch(self, request):
            return []

        async def health_check(self):
            return True

    MCPHandler.register(CustomProvider)
    handler = MCPHandler()
    caps = handler.list_capabilities()

    slack_cap = next(c for c in caps if c.provider_type == MCPProviderType.SLACK)
    assert slack_cap.provider_name == "CustomSlack"
    assert len(slack_cap.resources) == 1
    assert slack_cap.resources[0].uri == "slack://custom"


def test_mcp_server_capabilities_schema():
    cap = MCPServerCapabilities(
        provider_type=MCPProviderType.SLACK,
        provider_name="Test",
        version="2.0.0",
        supports_streaming=True,
    )
    assert cap.version == "2.0.0"
    assert cap.supports_streaming is True
    data = cap.model_dump(mode="json")
    assert data["provider_type"] == "slack"
    assert data["supports_streaming"] is True
