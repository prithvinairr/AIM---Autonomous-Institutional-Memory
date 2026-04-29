"""MCP (Model Context Protocol) Handler.

Aligned with MCP specification concepts:
  - Providers declare capabilities (resources + tools) via ``get_capabilities()``
  - ``list_resources()`` / ``list_tools()`` expose provider capabilities
  - ``fetch()`` dispatches context requests concurrently
  - Individual provider failures are non-fatal — logged and skipped

See: https://spec.modelcontextprotocol.io/
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import structlog

if TYPE_CHECKING:
    from aim.mcp.capability_negotiator import MCPCapabilityNegotiator

from aim.schemas.mcp import (
    ConfluenceContext,
    JiraContext,
    MCPContext,
    MCPContextRequest,
    MCPProviderType,
    MCPResource,
    MCPServerCapabilities,
    MCPTool,
    MCPToolCallResult,
    SlackContext,
)
from aim.utils.metrics import MCP_FETCH_LATENCY, MCP_ITEMS_FETCHED

log = structlog.get_logger(__name__)


def warn_if_transport_deprecated(transport: str) -> None:
    """Phase 13: emit a deprecation log when the caller selects a
    deprecated transport. Idempotent — safe to call at every startup.

    ``native`` is now rejected at config-validation time (see
    ``Settings._validate_mcp_transport``), so callers reaching this
    function with ``native`` indicates a stale env var being bypassed
    somewhere — we still log it rather than stay silent.
    """
    if transport == "native":
        log.warning(
            "mcp.native_transport_deprecated",
            transport=transport,
            recommendation="migrate to mcp_transport='stdio' or 'jsonrpc'",
        )


@runtime_checkable
class MCPProvider(Protocol):
    """MCP-aligned provider interface.

    Each provider declares its type and capabilities (resources it can read,
    tools it can invoke). This follows the MCP spec's initialize handshake
    where servers declare their capabilities.
    """
    provider_type: MCPProviderType

    async def fetch(self, request: MCPContextRequest) -> list[SlackContext | JiraContext]: ...
    async def health_check(self) -> bool: ...

    def get_capabilities(self) -> MCPServerCapabilities:
        """Declare provider capabilities (resources + tools).

        Default implementation returns an empty capability set.
        Override in concrete providers to advertise available resources/tools.
        """
        return MCPServerCapabilities(
            provider_type=self.provider_type,
            provider_name=type(self).__name__,
        )


class MCPHandler:
    """Orchestrates concurrent fetches across all registered MCP providers.

    Providers can be extended without modifying this class by using the
    ``@MCPHandler.register`` decorator::

        @MCPHandler.register
        class MyCustomSlackProvider:
            provider_type = MCPProviderType.SLACK
            async def fetch(self, request): ...
            async def health_check(self): ...

    The last registered provider for a given ``provider_type`` wins.
    Call ``MCPHandler.reset_registry()`` to revert to built-in defaults
    (useful in tests).
    """

    # Phase 13: registry state lives in MCPProviderRegistry. The
    # ``_provider_registry`` attribute below is a live pass-through to the
    # shared registry's internal dict — existing tests read it directly and
    # that access path must keep working.
    from aim.mcp.registry import get_shared_registry as _get_shared_registry
    _provider_registry = _get_shared_registry().as_dict()

    def __init__(self) -> None:
        from aim.mcp.registry import get_shared_registry

        registry = get_shared_registry()
        if not registry.is_empty():
            self._providers: dict[MCPProviderType, MCPProvider] = {
                ptype: cls()
                for ptype, cls in registry.as_dict().items()
            }
        else:
            from aim.mcp.slack_provider import SlackProvider
            from aim.mcp.jira_provider import JiraProvider

            self._providers = {
                MCPProviderType.SLACK: SlackProvider(),
                MCPProviderType.JIRA: JiraProvider(),
            }

    @classmethod
    def register(cls, provider_class: type) -> type:
        """Register a custom MCP provider (usable as a class decorator).

        The ``provider_class`` must expose a ``provider_type`` class attribute
        of type ``MCPProviderType`` and implement the ``MCPProvider`` Protocol.

        Phase 13: delegates to the shared ``MCPProviderRegistry``.
        """
        from aim.mcp.registry import get_shared_registry

        get_shared_registry().register(provider_class)
        return provider_class

    @classmethod
    def unregister(cls, provider_type: MCPProviderType) -> None:
        """Remove a provider from the registry."""
        from aim.mcp.registry import get_shared_registry

        get_shared_registry().unregister(provider_type)

    @classmethod
    def reset_registry(cls) -> None:
        """Clear the registry and revert to built-in default providers.

        Primarily intended for use in tests.
        """
        from aim.mcp.registry import get_shared_registry

        get_shared_registry().reset()

    async def fetch(self, request: MCPContextRequest) -> MCPContext:
        from aim.config import get_settings

        active = [self._providers[p] for p in request.providers if p in self._providers]
        if not active:
            return MCPContext()

        log.info("mcp_handler.fetch_start", providers=[p.provider_type for p in active])

        # Hard deadline across all providers combined
        handler_timeout = get_settings().mcp_handler_timeout_seconds

        tasks = [
            asyncio.create_task(
                self._safe_fetch(provider, request),
                name=f"mcp_{provider.provider_type}",
            )
            for provider in active
        ]

        try:
            async with asyncio.timeout(handler_timeout):
                results = await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.TimeoutError:
            log.error("mcp_handler.timeout", timeout=handler_timeout)
            for t in tasks:
                t.cancel()
            return MCPContext()

        slack_contexts: list[SlackContext] = []
        jira_contexts: list[JiraContext] = []
        confluence_contexts: list[ConfluenceContext] = []

        for provider, result in zip(active, results):
            if isinstance(result, Exception):
                log.error(
                    "mcp_handler.provider_error",
                    provider=provider.provider_type,
                    error=str(result),
                )
                continue
            for item in result:
                if isinstance(item, SlackContext):
                    slack_contexts.append(item)
                    MCP_ITEMS_FETCHED.labels(provider="slack").inc(len(item.messages))
                elif isinstance(item, JiraContext):
                    jira_contexts.append(item)
                    MCP_ITEMS_FETCHED.labels(provider="jira").inc(len(item.issues))
                elif isinstance(item, ConfluenceContext):
                    confluence_contexts.append(item)
                    MCP_ITEMS_FETCHED.labels(provider="confluence").inc(len(item.pages))

        ctx = MCPContext(
            slack_contexts=slack_contexts,
            jira_contexts=jira_contexts,
            confluence_contexts=confluence_contexts,
        )
        log.info("mcp_handler.fetch_done", total_items=ctx.total_items)
        return ctx

    async def _safe_fetch(
        self,
        provider: MCPProvider,
        request: MCPContextRequest,
    ) -> list[SlackContext | JiraContext]:
        from aim.config import get_settings

        t0 = time.perf_counter()
        try:
            async with asyncio.timeout(get_settings().mcp_provider_timeout_seconds):
                result = await provider.fetch(request)
            MCP_FETCH_LATENCY.labels(provider=provider.provider_type.value).observe(
                time.perf_counter() - t0
            )
            return result
        except asyncio.TimeoutError:
            log.error("mcp_handler.provider_timeout", provider=provider.provider_type)
            return []
        except Exception as exc:
            log.error("mcp_handler.provider_error", provider=provider.provider_type, error=str(exc))
            return []

    # ── MCP spec: capability discovery ──────────────────────────────────────

    def _negotiator(self) -> "MCPCapabilityNegotiator":
        """Build a negotiator bound to current providers + active transport.

        Constructed per-call because (a) provider dict can change between
        calls via register/unregister, and (b) the ``mcp_transport``
        setting is expected to be stable but re-reading it keeps behaviour
        identical to the pre-refactor inline path.
        """
        from aim.config import get_settings
        from aim.mcp.capability_negotiator import MCPCapabilityNegotiator

        return MCPCapabilityNegotiator(
            providers=self._providers,
            transport=get_settings().mcp_transport,
        )

    def list_capabilities(self) -> list[MCPServerCapabilities]:
        """Return capabilities for all registered providers (MCP: initialize).

        When MCP_TRANSPORT=stdio, also reports tools/resources discovered
        from the upstream subprocess (not just hardcoded in our code).
        """
        return self._negotiator().list_capabilities()

    def list_resources(self) -> list[MCPResource]:
        """List all resources across all providers (MCP: resources/list)."""
        return self._negotiator().list_resources()

    def list_tools(self) -> list[MCPTool]:
        """List all tools across all providers (MCP: tools/list)."""
        return self._negotiator().list_tools()

    # ── MCP spec: tools/call ─────────────────────────────────────────────────

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
    ) -> MCPToolCallResult:
        """Invoke a declared MCP tool by name (MCP spec: tools/call).

        Finds the provider that owns the tool, validates input,
        and dispatches the call.
        """
        for provider in self._providers.values():
            caps = provider.get_capabilities() if hasattr(provider, "get_capabilities") else None
            if not caps:
                continue
            for tool in caps.tools:
                if tool.name == tool_name:
                    try:
                        # Build a request from the tool arguments
                        request = MCPContextRequest(
                            query_text=arguments.get("query", ""),
                            providers=[provider.provider_type],
                            slack_channels=arguments.get("channels", []),
                            jira_projects=arguments.get("projects", []),
                            max_results_per_provider=arguments.get("max_results", 5),
                        )
                        results = await self._safe_fetch(provider, request)
                        return MCPToolCallResult(
                            tool_name=tool_name,
                            provider_type=provider.provider_type,
                            success=True,
                            data=results,
                        )
                    except Exception as exc:
                        log.error("mcp_handler.call_tool_error", tool=tool_name, error=str(exc))
                        return MCPToolCallResult(
                            tool_name=tool_name,
                            provider_type=provider.provider_type,
                            success=False,
                            error=str(exc),
                        )

        return MCPToolCallResult(
            tool_name=tool_name,
            provider_type=MCPProviderType.SLACK,  # placeholder
            success=False,
            error=f"Unknown tool: {tool_name}",
        )

    # ── MCP spec: resources/read ──────────────────────────────────────────────

    async def read_resource(self, uri: str) -> dict:
        """Read a declared MCP resource by URI (MCP spec: resources/read).

        Parses the URI scheme to route to the correct provider.
        """
        for provider in self._providers.values():
            caps = provider.get_capabilities() if hasattr(provider, "get_capabilities") else None
            if not caps:
                continue
            for resource in caps.resources:
                if resource.uri == uri or uri.startswith(resource.uri.rsplit("/", 1)[0]):
                    request = MCPContextRequest(
                        query_text="",
                        providers=[provider.provider_type],
                        max_results_per_provider=10,
                    )
                    results = await self._safe_fetch(provider, request)
                    return {
                        "uri": uri,
                        "provider": provider.provider_type.value,
                        "items": len(results),
                        "data": [
                            r.model_dump() if hasattr(r, "model_dump") else str(r)
                            for r in results
                        ],
                    }
        return {"uri": uri, "error": "Resource not found", "data": []}

    async def health_check(self) -> dict[str, bool]:
        results = await asyncio.gather(
            *[p.health_check() for p in self._providers.values()],
            return_exceptions=True,
        )
        return {
            ptype.value: (r if isinstance(r, bool) else False)
            for ptype, r in zip(self._providers.keys(), results)
        }
