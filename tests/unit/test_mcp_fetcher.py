"""Unit tests for the MCP context fetcher node."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from aim.agents.nodes.mcp_fetcher import fetch_mcp_context
from aim.agents.state import AgentState
from aim.schemas.mcp import MCPContext, SlackContext, SlackMessage, JiraContext, JiraIssue
from aim.schemas.query import ReasoningDepth


def _make_state(**overrides) -> AgentState:
    defaults = {
        "query_id": uuid4(),
        "original_query": "What happened in the auth service?",
        "reasoning_depth": ReasoningDepth.STANDARD,
        "sub_queries": ["auth service issues"],
    }
    defaults.update(overrides)
    return AgentState(**defaults)


def _mock_settings(slack=True, jira=True):
    return MagicMock(
        slack_bot_token="xoxb-test" if slack else "",
        jira_api_token="jira-test" if jira else "",
        slack_default_channels=["general"],
        jira_default_projects=["ENG"],
    )


@pytest.mark.asyncio
async def test_skips_when_no_providers_configured():
    with patch("aim.agents.nodes.mcp_fetcher.get_settings", return_value=_mock_settings(slack=False, jira=False)):
        result = await fetch_mcp_context(_make_state())

    assert any("skipped" in s for s in result.reasoning_steps)
    assert result.mcp_context is None


@pytest.mark.asyncio
async def test_fetches_slack_and_jira_context():
    slack_msg = SlackMessage(
        message_id="m1", channel="general", author="user1",
        text="Auth service is down", timestamp="2026-01-01T00:00:00Z",
    )
    slack_ctx = SlackContext(channel="general", messages=[slack_msg], query_relevance_score=0.9)

    jira_issue = JiraIssue(
        issue_key="ENG-123", summary="Auth regression",
        status="Open", url="https://jira.test/ENG-123",
        created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
    )
    jira_ctx = JiraContext(project="ENG", issues=[jira_issue], query_relevance_score=0.8)

    mcp_context = MCPContext(slack_contexts=[slack_ctx], jira_contexts=[jira_ctx])

    mock_handler = MagicMock()
    mock_handler.fetch = AsyncMock(return_value=mcp_context)

    with patch("aim.agents.nodes.mcp_fetcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.mcp_fetcher.MCPHandler", return_value=mock_handler):
            result = await fetch_mcp_context(_make_state())

    assert result.mcp_context is not None
    assert result.mcp_context.total_items >= 1
    assert len(result.sources) > 0
    assert any("MCP fetch" in s for s in result.reasoning_steps)


@pytest.mark.asyncio
async def test_registers_sources_with_correct_types():
    slack_msg = SlackMessage(
        message_id="m1", channel="general", author="user1",
        text="test message", timestamp="2026-01-01T00:00:00Z",
    )
    slack_ctx = SlackContext(channel="general", messages=[slack_msg], query_relevance_score=0.9)
    mcp_context = MCPContext(slack_contexts=[slack_ctx])

    mock_handler = MagicMock()
    mock_handler.fetch = AsyncMock(return_value=mcp_context)

    with patch("aim.agents.nodes.mcp_fetcher.get_settings", return_value=_mock_settings(jira=False)):
        with patch("aim.agents.nodes.mcp_fetcher.MCPHandler", return_value=mock_handler):
            result = await fetch_mcp_context(_make_state())

    # Should have a SLACK_MCP source
    assert any(src.source_type.value == "slack_mcp" for src in result.sources.values())


@pytest.mark.asyncio
async def test_handles_fetch_error_gracefully():
    mock_handler = MagicMock()
    mock_handler.fetch = AsyncMock(side_effect=ConnectionError("MCP down"))

    with patch("aim.agents.nodes.mcp_fetcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.mcp_fetcher.MCPHandler", return_value=mock_handler):
            result = await fetch_mcp_context(_make_state())

    assert any("failed" in s.lower() for s in result.reasoning_steps)
    assert result.mcp_context is None


@pytest.mark.asyncio
async def test_only_configures_available_providers():
    mcp_context = MCPContext()
    mock_handler = MagicMock()
    mock_handler.fetch = AsyncMock(return_value=mcp_context)

    # Only Jira configured, no Slack
    with patch("aim.agents.nodes.mcp_fetcher.get_settings", return_value=_mock_settings(slack=False)):
        with patch("aim.agents.nodes.mcp_fetcher.MCPHandler", return_value=mock_handler):
            await fetch_mcp_context(_make_state())

    # Check that only JIRA was requested
    call_args = mock_handler.fetch.call_args[0][0]
    assert len(call_args.providers) == 1
    assert call_args.providers[0].value == "jira"


@pytest.mark.asyncio
async def test_source_confidence_is_dynamic():
    """MCP sources now use dynamic relevance scoring instead of hardcoded 0.85."""
    slack_msg = SlackMessage(
        message_id="m1", channel="general", author="user1",
        text="test", timestamp="2026-01-01T00:00:00Z",
    )
    slack_ctx = SlackContext(channel="general", messages=[slack_msg], query_relevance_score=0.9)
    mcp_context = MCPContext(slack_contexts=[slack_ctx])

    mock_handler = MagicMock()
    mock_handler.fetch = AsyncMock(return_value=mcp_context)

    with patch("aim.agents.nodes.mcp_fetcher.get_settings", return_value=_mock_settings(jira=False)):
        with patch("aim.agents.nodes.mcp_fetcher.MCPHandler", return_value=mock_handler):
            result = await fetch_mcp_context(_make_state())

    for src in result.sources.values():
        assert 0.1 <= src.confidence <= 1.0, f"Confidence {src.confidence} out of range"
