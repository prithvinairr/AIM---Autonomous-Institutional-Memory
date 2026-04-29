"""MCP client transport Protocol — Phase 13.

``StdioMCPClient`` has been the only concrete transport since Phase 1,
but the plan allows for HTTP, WebSocket, or in-process transports in
future. This module makes the implicit contract explicit:

Any MCP client transport must support:

* ``start(env)`` / ``stop()`` — connection lifecycle.
* ``send(method, params, timeout)`` — JSON-RPC request expecting a
  correlated response; returns the server's ``result`` dict.
* ``notify(method, params)`` — JSON-RPC notification (no response).
* ``on_notification(method, handler)`` — subscribe to server-initiated
  messages (``notifications/progress`` etc.).
* ``alive`` — boolean property, true when the transport is connected.

The Protocol is ``@runtime_checkable`` so operator code and tests can
assert transport conformance with ``isinstance(transport, MCPClientTransport)``.
"""
from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class MCPClientTransport(Protocol):
    """Structural Protocol every MCP client transport must satisfy.

    Implementations live under ``aim/mcp/client/`` — currently only
    ``StdioMCPClient``. Future additions (HTTP, WebSocket, in-process)
    should conform to this interface so callers don't need to special-case.
    """

    @property
    def alive(self) -> bool:
        """True when ``start()`` has been called and the underlying
        transport (subprocess, socket, pipe) is still connected."""
        ...

    async def start(self, env: dict[str, str] | None = None) -> None:
        """Open the connection. ``env`` is only meaningful for transports
        that spawn subprocesses; ignored otherwise."""
        ...

    async def stop(self) -> None:
        """Close the connection gracefully. Safe to call multiple times."""
        ...

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Dispatch a JSON-RPC 2.0 request and await the correlated
        response. Raises on timeout or server-returned error envelope."""
        ...

    async def notify(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Dispatch a JSON-RPC 2.0 notification (no ``id``, no response)."""
        ...

    def on_notification(self, method: str, handler: Callable[[dict], Any]) -> None:
        """Register a handler for server-initiated notifications matching
        ``method``. Handlers are invoked with the ``params`` dict."""
        ...
