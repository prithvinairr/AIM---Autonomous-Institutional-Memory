"""Unit tests for the MCP handler orchestration."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.mcp.handler import MCPHandler
from aim.schemas.mcp import (
    JiraContext,
    JiraIssue,
    MCPContextRequest,
    MCPProviderType,
    SlackContext,
    SlackMessage,
)


def _make_request(**overrides):
    defaults = {
        "query_text": "test query",
        "providers": [MCPProviderType.SLACK, MCPProviderType.JIRA],
    }
    defaults.update(overrides)
    return MCPContextRequest(**defaults)


def _mock_settings():
    return MagicMock(
        mcp_handler_timeout_seconds=25.0,
        mcp_provider_timeout_seconds=15.0,
    )


@pytest.mark.asyncio
async def test_returns_empty_context_when_no_active_providers():
    handler = MCPHandler()
    request = _make_request(providers=[])
    ctx = await handler.fetch(request)
    assert ctx.total_items == 0


@pytest.mark.asyncio
async def test_concurrent_fetch_from_multiple_providers():
    slack_msg = SlackMessage(
        message_id="m1", channel="general", author="user1",
        text="test", timestamp="2026-01-01T00:00:00Z",
    )
    slack_ctx = SlackContext(channel="general", messages=[slack_msg], query_relevance_score=0.9)

    jira_issue = JiraIssue(
        issue_key="ENG-1", summary="Test", status="Open",
        url="https://jira.test/ENG-1",
        created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
    )
    jira_ctx = JiraContext(project="ENG", issues=[jira_issue], query_relevance_score=0.8)

    mock_slack = MagicMock()
    mock_slack.provider_type = MCPProviderType.SLACK
    mock_slack.fetch = AsyncMock(return_value=[slack_ctx])

    mock_jira = MagicMock()
    mock_jira.provider_type = MCPProviderType.JIRA
    mock_jira.fetch = AsyncMock(return_value=[jira_ctx])

    handler = MCPHandler()
    handler._providers = {
        MCPProviderType.SLACK: mock_slack,
        MCPProviderType.JIRA: mock_jira,
    }

    with patch("aim.config.get_settings", return_value=_mock_settings()):
        ctx = await handler.fetch(_make_request())

    assert len(ctx.slack_contexts) == 1
    assert len(ctx.jira_contexts) == 1
    assert ctx.total_items == 2


@pytest.mark.asyncio
async def test_individual_provider_failure_is_non_fatal():
    mock_slack = MagicMock()
    mock_slack.provider_type = MCPProviderType.SLACK
    mock_slack.fetch = AsyncMock(side_effect=ConnectionError("Slack down"))

    jira_issue = JiraIssue(
        issue_key="ENG-1", summary="Test", status="Open",
        url="https://jira.test/ENG-1",
        created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
    )
    jira_ctx = JiraContext(project="ENG", issues=[jira_issue], query_relevance_score=0.8)

    mock_jira = MagicMock()
    mock_jira.provider_type = MCPProviderType.JIRA
    mock_jira.fetch = AsyncMock(return_value=[jira_ctx])

    handler = MCPHandler()
    handler._providers = {
        MCPProviderType.SLACK: mock_slack,
        MCPProviderType.JIRA: mock_jira,
    }

    with patch("aim.config.get_settings", return_value=_mock_settings()):
        ctx = await handler.fetch(_make_request())

    # Slack failed but Jira succeeded
    assert len(ctx.slack_contexts) == 0
    assert len(ctx.jira_contexts) == 1


@pytest.mark.asyncio
async def test_health_check_returns_provider_status():
    mock_slack = MagicMock()
    mock_slack.provider_type = MCPProviderType.SLACK
    mock_slack.health_check = AsyncMock(return_value=True)

    mock_jira = MagicMock()
    mock_jira.provider_type = MCPProviderType.JIRA
    mock_jira.health_check = AsyncMock(return_value=False)

    handler = MCPHandler()
    handler._providers = {
        MCPProviderType.SLACK: mock_slack,
        MCPProviderType.JIRA: mock_jira,
    }

    result = await handler.health_check()
    assert result["slack"] is True
    assert result["jira"] is False


@pytest.mark.asyncio
async def test_register_decorator_adds_provider():
    MCPHandler.reset_registry()

    @MCPHandler.register
    class CustomProvider:
        provider_type = MCPProviderType.SLACK
        async def fetch(self, request):
            return []
        async def health_check(self):
            return True

    assert MCPProviderType.SLACK in MCPHandler._provider_registry
    MCPHandler.reset_registry()


@pytest.mark.asyncio
async def test_unregister_removes_provider():
    MCPHandler.reset_registry()

    @MCPHandler.register
    class Temp:
        provider_type = MCPProviderType.JIRA
        async def fetch(self, request):
            return []
        async def health_check(self):
            return True

    MCPHandler.unregister(MCPProviderType.JIRA)
    assert MCPProviderType.JIRA not in MCPHandler._provider_registry
    MCPHandler.reset_registry()


# ═══════════════════════════════════════════════════════════════════════════════
# Coverage for uncovered lines
# ═══════════════════════════════════════════════════════════════════════════════

from aim.schemas.mcp import (
    ConfluenceContext,
    ConfluencePage,
    MCPServerCapabilities,
    MCPTool,
)


@pytest.mark.asyncio
async def test_get_capabilities_default_returns_empty_capabilities():
    """Line 55: MCPProvider.get_capabilities() default return."""

    class BareProvider:
        provider_type = MCPProviderType.SLACK

        async def fetch(self, request):
            return []

        async def health_check(self):
            return True

    from aim.mcp.handler import MCPProvider

    provider = BareProvider()
    # The Protocol defines get_capabilities with a default body; invoke it
    # via the Protocol directly since BareProvider doesn't override it.
    caps = MCPProvider.get_capabilities(provider)
    assert isinstance(caps, MCPServerCapabilities)
    assert caps.provider_type == MCPProviderType.SLACK
    assert caps.provider_name == "BareProvider"
    assert caps.resources == []
    assert caps.tools == []


@pytest.mark.asyncio
async def test_fetch_handler_timeout_returns_empty_context():
    """Lines 148-152: asyncio.TimeoutError handling in fetch()."""
    mock_provider = MagicMock()
    mock_provider.provider_type = MCPProviderType.SLACK

    # Make fetch hang forever so the handler-level timeout fires
    async def hang_forever(request):
        await asyncio.sleep(999)

    mock_provider.fetch = hang_forever

    handler = MCPHandler()
    handler._providers = {MCPProviderType.SLACK: mock_provider}

    settings = _mock_settings()
    settings.mcp_handler_timeout_seconds = 0.01  # very short timeout
    settings.mcp_provider_timeout_seconds = 10.0

    with patch("aim.config.get_settings", return_value=settings):
        ctx = await handler.fetch(_make_request(providers=[MCPProviderType.SLACK]))

    assert ctx.total_items == 0
    assert ctx.slack_contexts == []


@pytest.mark.asyncio
async def test_fetch_provider_exception_in_results_loop():
    """Lines 160-165: Exception handling in fetch provider results loop."""
    mock_provider = MagicMock()
    mock_provider.provider_type = MCPProviderType.SLACK
    # _safe_fetch will return this exception as a result via gather(return_exceptions=True)
    mock_provider.fetch = AsyncMock(side_effect=RuntimeError("boom"))

    handler = MCPHandler()
    handler._providers = {MCPProviderType.SLACK: mock_provider}

    with patch("aim.config.get_settings", return_value=_mock_settings()):
        ctx = await handler.fetch(_make_request(providers=[MCPProviderType.SLACK]))

    # The exception is caught and logged; empty context returned
    assert ctx.slack_contexts == []
    assert ctx.total_items == 0


@pytest.mark.asyncio
async def test_fetch_confluence_context_handling():
    """Lines 173-175: ConfluenceContext handling in fetch."""
    page = ConfluencePage(
        page_id="p1",
        title="Test Page",
        space_key="ENG",
        body_text="content",
    )
    confluence_ctx = ConfluenceContext(
        space_key="ENG", pages=[page], query_relevance_score=0.9,
    )

    mock_provider = MagicMock()
    mock_provider.provider_type = MCPProviderType.CONFLUENCE
    mock_provider.fetch = AsyncMock(return_value=[confluence_ctx])

    handler = MCPHandler()
    handler._providers = {MCPProviderType.CONFLUENCE: mock_provider}

    with patch("aim.config.get_settings", return_value=_mock_settings()):
        ctx = await handler.fetch(
            _make_request(providers=[MCPProviderType.CONFLUENCE])
        )

    assert len(ctx.confluence_contexts) == 1
    assert ctx.confluence_contexts[0].space_key == "ENG"


@pytest.mark.asyncio
async def test_safe_fetch_timeout_returns_empty_list():
    """Lines 201-202: asyncio.TimeoutError in _safe_fetch()."""
    mock_provider = MagicMock()
    mock_provider.provider_type = MCPProviderType.SLACK

    async def slow_fetch(request):
        await asyncio.sleep(999)

    mock_provider.fetch = slow_fetch

    handler = MCPHandler()

    settings = _mock_settings()
    settings.mcp_provider_timeout_seconds = 0.01

    with patch("aim.config.get_settings", return_value=settings):
        result = await handler._safe_fetch(mock_provider, _make_request())

    assert result == []


@pytest.mark.asyncio
async def test_list_capabilities_default_fallback():
    """Line 216: default capabilities for providers without get_capabilities."""
    mock_provider = MagicMock(spec=[])  # spec=[] means NO attributes
    mock_provider.provider_type = MCPProviderType.SLACK
    type(mock_provider).__name__ = "FakeSlack"

    handler = MCPHandler()
    handler._providers = {MCPProviderType.SLACK: mock_provider}

    caps = handler.list_capabilities()
    assert len(caps) == 1
    assert caps[0].provider_type == MCPProviderType.SLACK
    assert caps[0].provider_name == "FakeSlack"


@pytest.mark.asyncio
async def test_call_tool_skips_provider_without_capabilities():
    """Line 251: if not caps: continue in call_tool()."""
    mock_provider = MagicMock(spec=[])  # no get_capabilities
    mock_provider.provider_type = MCPProviderType.SLACK

    handler = MCPHandler()
    handler._providers = {MCPProviderType.SLACK: mock_provider}

    result = await handler.call_tool("some_tool", {"query": "test"})
    assert result.success is False
    assert "Unknown tool" in result.error


@pytest.mark.asyncio
async def test_read_resource_skips_provider_without_capabilities():
    """Line 296: if not caps: continue in read_resource()."""
    mock_provider = MagicMock(spec=[])  # no get_capabilities
    mock_provider.provider_type = MCPProviderType.SLACK

    handler = MCPHandler()
    handler._providers = {MCPProviderType.SLACK: mock_provider}

    result = await handler.read_resource("slack://channel/general")
    assert result["error"] == "Resource not found"
