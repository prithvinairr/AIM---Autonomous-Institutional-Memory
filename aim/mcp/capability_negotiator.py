"""MCP capability negotiation — pure aggregation over providers.

Extracted from ``MCPHandler`` in Phase 13. Before this split, the handler
did three things at once: orchestrate concurrent fetches, manage the
provider registry, and aggregate capability declarations. Only the last
is pure (no I/O, no async), so it moves here where it can be tested in
isolation.

Given a ``{provider_type: provider_instance}`` dict and the active
transport name, this class answers three MCP-spec questions:

* ``list_capabilities()`` — one ``MCPServerCapabilities`` per provider,
  with the active transport stamped on every entry.
* ``list_resources()`` — flat list across all providers.
* ``list_tools()`` — flat list across all providers.

Providers that don't implement ``get_capabilities()`` still appear, but
with an empty resources/tools set (backwards compat with legacy providers).
"""
from __future__ import annotations

from typing import Mapping

from aim.schemas.mcp import (
    MCPProviderType,
    MCPResource,
    MCPServerCapabilities,
    MCPTool,
)


class MCPCapabilityNegotiator:
    """Aggregates provider-declared capabilities for MCP discovery.

    Stateless beyond the injected provider map and transport. Safe to
    instantiate per-call — nothing here caches between invocations.
    """

    __slots__ = ("_providers", "_transport")

    def __init__(
        self,
        providers: Mapping[MCPProviderType, object],
        transport: str,
    ) -> None:
        self._providers = providers
        self._transport = transport

    def list_capabilities(self) -> list[MCPServerCapabilities]:
        """Return one capability object per registered provider.

        The active transport is overlaid on every entry so callers don't
        have to thread it through separately. Legacy providers without
        ``get_capabilities`` get a minimal synthesised entry rather than
        being silently dropped.
        """
        caps: list[MCPServerCapabilities] = []
        for provider in self._providers.values():
            get_caps = getattr(provider, "get_capabilities", None)
            if callable(get_caps):
                cap = get_caps()
                # MCPServerCapabilities is a frozen pydantic model — can't
                # assign fields. model_copy returns a new instance with the
                # transport field updated.
                caps.append(cap.model_copy(update={"transport": self._transport}))
            else:
                caps.append(MCPServerCapabilities(
                    provider_type=provider.provider_type,
                    provider_name=type(provider).__name__,
                    transport=self._transport,
                ))
        return caps

    def list_resources(self) -> list[MCPResource]:
        """Flat list of every resource across every provider."""
        resources: list[MCPResource] = []
        for cap in self.list_capabilities():
            resources.extend(cap.resources)
        return resources

    def list_tools(self) -> list[MCPTool]:
        """Flat list of every tool across every provider."""
        tools: list[MCPTool] = []
        for cap in self.list_capabilities():
            tools.extend(cap.tools)
        return tools
