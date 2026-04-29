"""MCP client session — manages the lifecycle of an upstream MCP server.

Handles the ``initialize`` handshake, caches ``tools/list`` and
``resources/list`` results, and exposes ``call_tool`` / ``read_resource``
convenience methods.

Usage::

    session = MCPClientSession(MCPProviderType.SLACK)
    await session.start()
    tools = await session.list_tools()
    result = await session.call_tool("slack_search", {"query": "outage"})
    await session.stop()
"""
from __future__ import annotations

import structlog

from aim.config import get_settings
from aim.mcp.client.registry import get_server_spec
from aim.mcp.client.stdio_client import StdioMCPClient
from aim.schemas.mcp import MCPProviderType

log = structlog.get_logger(__name__)

_MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPClientSession:
    """Manages a single upstream MCP server subprocess."""

    def __init__(self, provider_type: MCPProviderType) -> None:
        self.provider_type = provider_type
        self._client: StdioMCPClient | None = None
        self._server_info: dict | None = None
        self._capabilities: dict | None = None
        self._tools_cache: list[dict] | None = None
        self._resources_cache: list[dict] | None = None

    @property
    def alive(self) -> bool:
        return self._client is not None and self._client.alive

    async def start(self) -> None:
        """Spawn the MCP server and perform the initialize handshake."""
        spec = get_server_spec(self.provider_type)
        if spec is None:
            raise ValueError(f"No MCP server spec registered for {self.provider_type}")

        settings = get_settings()
        env = spec.build_env(settings)

        # Resolve placeholders in args (e.g. {jira_base_url})
        resolved_args = []
        for arg in spec.args:
            if arg.startswith("{") and arg.endswith("}"):
                attr = arg[1:-1]
                val = getattr(settings, attr, "")
                resolved_args.append(str(val))
            else:
                resolved_args.append(arg)

        self._client = StdioMCPClient(command=spec.command, args=resolved_args)
        await self._client.start(env=env)

        # MCP initialize handshake
        try:
            result = await self._client.send("initialize", {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "capabilities": {
                    "roots": {"listChanged": False},
                    "sampling": {},
                },
                "clientInfo": {
                    "name": "aim",
                    "version": settings.app_version,
                },
            })
            self._server_info = result.get("serverInfo", {})
            self._capabilities = result.get("capabilities", {})

            # Validate server's protocol version is compatible
            server_version = result.get("protocolVersion", "")
            if server_version and server_version != _MCP_PROTOCOL_VERSION:
                # Log warning but don't fail — servers may use newer minor versions
                log.warning(
                    "mcp_session.protocol_version_mismatch",
                    provider=self.provider_type.value,
                    client_version=_MCP_PROTOCOL_VERSION,
                    server_version=server_version,
                )

            # Spec-compliant acknowledgement: notify the server that
            # initialization is complete before issuing any other requests.
            try:
                await self._client.notify("notifications/initialized", {})
            except Exception as exc:
                log.debug(
                    "mcp_session.initialized_notify_skipped",
                    provider=self.provider_type.value,
                    error=str(exc),
                )

            log.info(
                "mcp_session.initialized",
                provider=self.provider_type.value,
                server=self._server_info.get("name", "unknown"),
                version=self._server_info.get("version", "unknown"),
                has_prompts=bool(self._capabilities.get("prompts")),
                has_resources=bool(self._capabilities.get("resources")),
                has_tools=bool(self._capabilities.get("tools")),
            )
        except Exception as exc:
            log.error("mcp_session.initialize_failed", provider=self.provider_type.value, error=str(exc))
            await self.stop()
            raise

    async def stop(self) -> None:
        """Shut down the MCP server subprocess."""
        if self._client:
            await self._client.stop()
            self._client = None
        self._tools_cache = None
        self._resources_cache = None

    async def list_tools(self) -> list[dict]:
        """Discover tools from the upstream MCP server (cached after first call)."""
        if self._tools_cache is not None:
            return self._tools_cache
        if not self.alive:
            return []
        result = await self._client.send("tools/list")  # type: ignore[union-attr]
        self._tools_cache = result.get("tools", [])
        return self._tools_cache

    async def list_resources(self) -> list[dict]:
        """Discover resources from the upstream MCP server (cached after first call)."""
        if self._resources_cache is not None:
            return self._resources_cache
        if not self.alive:
            return []
        result = await self._client.send("resources/list")  # type: ignore[union-attr]
        self._resources_cache = result.get("resources", [])
        return self._resources_cache

    def invalidate_resource_cache(self) -> None:
        """Drop the cached resources/list so the next call re-fetches.

        Called by the notification handler when the server pushes
        ``notifications/resources/updated`` — ensures we never serve stale
        resource metadata after the upstream server reloads its state.
        """
        self._resources_cache = None
        log.debug("mcp_session.resources_cache_invalidated", provider=self.provider_type.value)

    async def list_prompts(self) -> list[dict]:
        """Discover prompts from the upstream MCP server (MCP: prompts/list).

        Returns an empty list if the server does not advertise prompts capability
        or the method is unsupported.
        """
        if not self.alive:
            return []
        if self._capabilities is not None and not self._capabilities.get("prompts"):
            return []
        try:
            result = await self._client.send("prompts/list")  # type: ignore[union-attr]
            return result.get("prompts", [])
        except Exception as exc:
            log.debug("mcp_session.prompts_list_unsupported", error=str(exc))
            return []

    async def get_prompt(self, name: str, arguments: dict | None = None) -> dict:
        """Retrieve a prompt template from the upstream MCP server (MCP: prompts/get)."""
        if not self.alive:
            raise RuntimeError(f"MCP session for {self.provider_type.value} is not running")
        return await self._client.send("prompts/get", {  # type: ignore[union-attr]
            "name": name,
            "arguments": arguments or {},
        })

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        """Invoke a tool on the upstream MCP server (MCP: tools/call)."""
        if not self.alive:
            raise RuntimeError(f"MCP session for {self.provider_type.value} is not running")
        return await self._client.send("tools/call", {  # type: ignore[union-attr]
            "name": name,
            "arguments": arguments or {},
        })

    async def read_resource(self, uri: str) -> dict:
        """Read a resource from the upstream MCP server (MCP: resources/read)."""
        if not self.alive:
            raise RuntimeError(f"MCP session for {self.provider_type.value} is not running")
        return await self._client.send("resources/read", {"uri": uri})  # type: ignore[union-attr]

    async def ping(self) -> bool:
        """Send MCP ping keepalive. Returns True if server responds, False otherwise."""
        if not self.alive:
            return False
        try:
            await self._client.send("ping", {})  # type: ignore[union-attr]
            return True
        except Exception:
            return False

    async def subscribe_resource(self, uri: str) -> None:
        """Subscribe to resource change notifications (MCP: resources/subscribe)."""
        if not self.alive:
            return
        if self._capabilities and not self._capabilities.get("resources", {}).get("subscribe"):
            return  # server doesn't support subscriptions
        try:
            await self._client.send("resources/subscribe", {"uri": uri})  # type: ignore[union-attr]
        except Exception as exc:
            log.debug("mcp_session.subscribe_failed", uri=uri, error=str(exc))

    async def unsubscribe_resource(self, uri: str) -> None:
        """Unsubscribe from resource change notifications (MCP: resources/unsubscribe)."""
        if not self.alive:
            return
        try:
            await self._client.send("resources/unsubscribe", {"uri": uri})  # type: ignore[union-attr]
        except Exception as exc:
            log.debug("mcp_session.unsubscribe_failed", uri=uri, error=str(exc))


class MCPSessionPool:
    """Manages a pool of MCPClientSession instances — one per provider type.

    Sessions are lazily started on first use and reused across requests.
    """

    _MAX_RESPAWNS = 3  # per provider, to prevent restart storms

    def __init__(self) -> None:
        self._sessions: dict[MCPProviderType, MCPClientSession] = {}

    async def get_session(self, provider_type: MCPProviderType) -> MCPClientSession:
        """Get or create a session for the given provider type.

        If a previously-alive session has died (subprocess crash), this
        transparently respawns it — up to ``_MAX_RESPAWNS`` times per
        provider — so callers never see a permanent dead session.
        """
        session = self._sessions.get(provider_type)
        if session is not None and session.alive:
            return session

        # Respawn tracking: prevent infinite restart loops
        respawn_key = f"_respawns_{provider_type.value}"
        respawn_count = getattr(self, respawn_key, 0)
        if session is not None and not session.alive and respawn_count < self._MAX_RESPAWNS:
            log.warning(
                "mcp_pool.respawning",
                provider=provider_type.value,
                attempt=respawn_count + 1,
            )
            try:
                await session.stop()
            except Exception:
                pass
            setattr(self, respawn_key, respawn_count + 1)

        session = MCPClientSession(provider_type)
        await session.start()

        # Reset respawn counter on successful start — a recovered provider
        # should get a fresh quota of _MAX_RESPAWNS for future crashes.
        setattr(self, respawn_key, 0)

        # Register resource invalidation notification handler
        client = getattr(session, '_client', None)
        if client is not None and hasattr(client, 'on_notification'):
            client.on_notification(
                "notifications/resources/updated",
                lambda params: session.invalidate_resource_cache(),
            )

        self._sessions[provider_type] = session
        return session

    async def shutdown(self) -> None:
        """Stop all sessions."""
        for session in self._sessions.values():
            try:
                await session.stop()
            except Exception as exc:
                log.warning("mcp_pool.stop_error", error=str(exc))
        self._sessions.clear()

    def health(self) -> dict[str, bool]:
        """Report health of each session."""
        return {
            pt.value: session.alive
            for pt, session in self._sessions.items()
        }


# Module-level singleton
_pool: MCPSessionPool | None = None


def get_session_pool() -> MCPSessionPool:
    global _pool
    if _pool is None:
        _pool = MCPSessionPool()
    return _pool


def reset_session_pool() -> None:
    global _pool
    _pool = None
