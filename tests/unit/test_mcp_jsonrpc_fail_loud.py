"""Phase α.2 step 1 — providers fail loudly when transport='jsonrpc'.

``jsonrpc`` is a reserved-but-unimplemented transport value. The config
validator accepts it (reserved for a future HTTP client), but no provider
actually speaks it. Previously, selecting it silently fell through to the
REST scraper path — the operator thought they had MCP protocol adherence
and actually had none.

This pins the contract: instantiating SlackProvider or JiraProvider with
mcp_transport='jsonrpc' raises NotImplementedError at __init__ time,
before any fetch can run. Fail loud, not silent.

Note: config.Settings validation accepts 'jsonrpc' as reserved. These
tests monkeypatch get_settings() to bypass that and assert the provider
defends itself regardless.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


class _FakeSettings(SimpleNamespace):
    """Minimal settings stub — only fields the providers touch at init."""


def _install_fake_settings(monkeypatch, transport: str) -> None:
    fake = _FakeSettings(
        mcp_transport=transport,
        slack_bot_token="xoxb-test",
        slack_default_channels=[],
        jira_email="test@example.com",
        jira_api_token="token",
        jira_base_url="https://example.atlassian.net",
        jira_default_projects=[],
        mcp_provider_timeout_seconds=10,
    )
    # Both providers call `get_settings()` at the top of __init__ via the
    # module-level import. Patch both module references.
    import aim.mcp.slack_provider as slack_mod
    import aim.mcp.jira_provider as jira_mod

    monkeypatch.setattr(slack_mod, "get_settings", lambda: fake)
    monkeypatch.setattr(jira_mod, "get_settings", lambda: fake)


class TestJsonRpcFailsLoud:
    def test_slack_provider_raises_on_jsonrpc(self, monkeypatch):
        _install_fake_settings(monkeypatch, "jsonrpc")
        from aim.mcp.slack_provider import SlackProvider

        with pytest.raises(NotImplementedError) as excinfo:
            SlackProvider()
        msg = str(excinfo.value)
        # Message must name the provider so logs are diagnosable, and
        # point operators at the working alternative ('stdio').
        assert "SlackProvider" in msg
        assert "jsonrpc" in msg
        assert "stdio" in msg

    def test_jira_provider_raises_on_jsonrpc(self, monkeypatch):
        _install_fake_settings(monkeypatch, "jsonrpc")
        from aim.mcp.jira_provider import JiraProvider

        with pytest.raises(NotImplementedError) as excinfo:
            JiraProvider()
        msg = str(excinfo.value)
        assert "JiraProvider" in msg
        assert "jsonrpc" in msg
        assert "stdio" in msg


class TestOtherTransportsStillConstruct:
    """Regression guard: the fail-loud branch must not catch stdio or the
    REST default. Only 'jsonrpc' should raise."""

    def test_slack_provider_builds_on_stdio(self, monkeypatch):
        _install_fake_settings(monkeypatch, "stdio")
        from aim.mcp.slack_provider import SlackProvider

        provider = SlackProvider()
        assert provider._transport == "stdio"

    def test_jira_provider_builds_on_stdio(self, monkeypatch):
        _install_fake_settings(monkeypatch, "stdio")
        from aim.mcp.jira_provider import JiraProvider

        provider = JiraProvider()
        assert provider._transport == "stdio"
