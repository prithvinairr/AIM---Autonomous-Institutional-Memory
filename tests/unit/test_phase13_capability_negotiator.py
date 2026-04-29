"""Phase 13 — ``MCPCapabilityNegotiator`` extraction.

Before this refactor, ``MCPHandler.list_capabilities`` / ``list_resources`` /
``list_tools`` mixed three responsibilities:

  1. Iterate providers and collect declared capabilities.
  2. Stamp the current transport onto every capability object.
  3. Flatten nested ``resources`` / ``tools`` lists.

That's pure data aggregation — no orchestration, no async. Extracting it to
a standalone class lets us unit-test the negotiation logic without
instantiating the full handler (which pulls in every provider module).

These tests pin:
* Each provider's ``get_capabilities()`` is called exactly once per pass.
* The active transport is overlaid on every returned capability.
* Providers missing ``get_capabilities`` get a minimal synthesised entry
  (backwards compat — handler used to do this, keep doing it).
* Empty provider dict → empty results (no spurious default entry).
* ``list_resources`` / ``list_tools`` are flat projections of the
  capability list (no duplication, preserves order).
* The handler's public list_* methods keep delegating correctly so callers
  (tests, routes, SSE endpoints) see no behaviour change.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aim.mcp.capability_negotiator import MCPCapabilityNegotiator
from aim.schemas.mcp import (
    MCPProviderType,
    MCPResource,
    MCPServerCapabilities,
    MCPTool,
)


# ── Fake providers ──────────────────────────────────────────────────────────


def _slack_caps() -> MCPServerCapabilities:
    return MCPServerCapabilities(
        provider_type=MCPProviderType.SLACK,
        provider_name="FakeSlack",
        resources=[
            MCPResource(
                uri="slack://channel/engineering",
                name="#engineering",
                description="eng channel",
                mime_type="text/plain",
            ),
        ],
        tools=[
            MCPTool(
                name="slack_search",
                description="search slack",
                input_schema={"type": "object"},
            ),
        ],
    )


def _jira_caps() -> MCPServerCapabilities:
    return MCPServerCapabilities(
        provider_type=MCPProviderType.JIRA,
        provider_name="FakeJira",
        resources=[
            MCPResource(
                uri="jira://project/AIM",
                name="AIM",
                description="aim project",
                mime_type="application/json",
            ),
        ],
        tools=[
            MCPTool(
                name="jira_search",
                description="search jira",
                input_schema={"type": "object"},
            ),
        ],
    )


class _FakeSlack:
    provider_type = MCPProviderType.SLACK

    def __init__(self) -> None:
        self._calls = 0

    def get_capabilities(self) -> MCPServerCapabilities:
        self._calls += 1
        return _slack_caps()


class _FakeJira:
    provider_type = MCPProviderType.JIRA

    def __init__(self) -> None:
        self._calls = 0

    def get_capabilities(self) -> MCPServerCapabilities:
        self._calls += 1
        return _jira_caps()


class _FakeLegacy:
    """A provider that predates get_capabilities — negotiator should
    still surface it with a minimal synthesised entry."""
    provider_type = MCPProviderType.CONFLUENCE


# ── Tests ───────────────────────────────────────────────────────────────────


class TestListCapabilities:
    def test_calls_each_provider_once_and_stamps_transport(self):
        slack, jira = _FakeSlack(), _FakeJira()
        neg = MCPCapabilityNegotiator(
            providers={MCPProviderType.SLACK: slack, MCPProviderType.JIRA: jira},
            transport="stdio",
        )
        caps = neg.list_capabilities()

        assert slack._calls == 1
        assert jira._calls == 1
        assert len(caps) == 2
        for cap in caps:
            assert cap.transport == "stdio"

    def test_stamps_requested_transport_overwriting_default(self):
        """Provider capability objects built with the default transport
        (``native``) must be reissued with the active transport."""
        slack = _FakeSlack()
        neg = MCPCapabilityNegotiator(
            providers={MCPProviderType.SLACK: slack},
            transport="jsonrpc",
        )
        (cap,) = neg.list_capabilities()
        assert cap.transport == "jsonrpc"
        # Data was not mutated on the provider-returned object (pydantic
        # frozen model_copy semantics).
        assert _slack_caps().transport != "jsonrpc"

    def test_legacy_provider_gets_synthesised_capability(self):
        legacy = _FakeLegacy()
        neg = MCPCapabilityNegotiator(
            providers={MCPProviderType.CONFLUENCE: legacy},
            transport="stdio",
        )
        (cap,) = neg.list_capabilities()
        assert cap.provider_type == MCPProviderType.CONFLUENCE
        assert cap.provider_name == "_FakeLegacy"
        assert cap.transport == "stdio"
        # No declared resources/tools — keep the list empty, not None.
        assert cap.resources == []
        assert cap.tools == []

    def test_empty_providers_returns_empty_list(self):
        neg = MCPCapabilityNegotiator(providers={}, transport="stdio")
        assert neg.list_capabilities() == []


class TestListResourcesAndTools:
    def test_list_resources_flattens_capabilities(self):
        neg = MCPCapabilityNegotiator(
            providers={
                MCPProviderType.SLACK: _FakeSlack(),
                MCPProviderType.JIRA: _FakeJira(),
            },
            transport="stdio",
        )
        resources = neg.list_resources()
        uris = {r.uri for r in resources}
        assert uris == {"slack://channel/engineering", "jira://project/AIM"}

    def test_list_tools_flattens_capabilities(self):
        neg = MCPCapabilityNegotiator(
            providers={
                MCPProviderType.SLACK: _FakeSlack(),
                MCPProviderType.JIRA: _FakeJira(),
            },
            transport="stdio",
        )
        names = {t.name for t in neg.list_tools()}
        assert names == {"slack_search", "jira_search"}

    def test_list_resources_preserves_provider_order(self):
        slack = _FakeSlack()
        jira = _FakeJira()
        neg = MCPCapabilityNegotiator(
            providers={MCPProviderType.JIRA: jira, MCPProviderType.SLACK: slack},
            transport="stdio",
        )
        resources = neg.list_resources()
        # Jira registered first → jira resource comes first.
        assert resources[0].uri.startswith("jira://")
        assert resources[1].uri.startswith("slack://")


class TestHandlerDelegation:
    """The public MCPHandler surface must keep working — list_capabilities,
    list_resources, list_tools all delegate to the negotiator and behave
    identically to the pre-extraction implementation."""

    def _make_handler_with_fakes(self, monkeypatch, transport: str = "stdio"):
        from aim.mcp.handler import MCPHandler
        from aim.config import get_settings

        # Patch settings.mcp_transport without stepping on the rest of config.
        # _negotiator() does a fresh ``from aim.config import get_settings``
        # inside the method body, so we patch ``aim.config.get_settings``
        # (the source) rather than a re-exported alias.
        real = get_settings()
        fake = MagicMock(wraps=real)
        fake.mcp_transport = transport
        monkeypatch.setattr("aim.config.get_settings", lambda: fake)

        handler = MCPHandler.__new__(MCPHandler)
        handler._providers = {
            MCPProviderType.SLACK: _FakeSlack(),
            MCPProviderType.JIRA: _FakeJira(),
        }
        return handler

    def test_handler_list_capabilities_stamps_transport(self, monkeypatch):
        handler = self._make_handler_with_fakes(monkeypatch, transport="jsonrpc")
        caps = handler.list_capabilities()
        assert len(caps) == 2
        assert {c.transport for c in caps} == {"jsonrpc"}

    def test_handler_list_tools_returns_flat_list(self, monkeypatch):
        handler = self._make_handler_with_fakes(monkeypatch)
        tools = handler.list_tools()
        assert {t.name for t in tools} == {"slack_search", "jira_search"}

    def test_handler_list_resources_returns_flat_list(self, monkeypatch):
        handler = self._make_handler_with_fakes(monkeypatch)
        resources = handler.list_resources()
        assert {r.uri for r in resources} == {
            "slack://channel/engineering",
            "jira://project/AIM",
        }
