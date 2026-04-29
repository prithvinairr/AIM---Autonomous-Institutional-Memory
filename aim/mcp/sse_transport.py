"""Server-Sent Events (SSE) transport for MCP.

Implements the MCP transport specification's SSE framing layer:
  - ``GET /mcp/sse`` — initiates an SSE event stream, sends the ``endpoint``
    event with the messages URL, then maintains a keepalive stream.
  - ``POST /mcp/messages`` — receives JSON-RPC 2.0 requests and dispatches
    them via the existing ``JsonRpcTransport``.

SSE framing format::

    event: endpoint
    data: /mcp/messages

    event: message
    data: {"jsonrpc":"2.0","id":1,"result":{...}}

    event: ping
    data: keepalive

See: https://spec.modelcontextprotocol.io/specification/2024-11-05/basic/transports/#http-with-sse
"""
from __future__ import annotations

import asyncio
import time
from typing import AsyncGenerator

import structlog

from aim.mcp.jsonrpc import get_transport

log = structlog.get_logger(__name__)

# Keepalive interval in seconds
KEEPALIVE_INTERVAL = 15.0


def format_sse_event(event: str, data: str) -> str:
    """Format a single SSE event with proper framing."""
    lines = data.split("\n")
    formatted = f"event: {event}\n"
    for line in lines:
        formatted += f"data: {line}\n"
    formatted += "\n"
    return formatted


class SSESession:
    """Represents an active SSE connection session.

    Tracks the session ID and message queue for bidirectional
    communication via the SSE + POST message pattern.
    """

    def __init__(self, session_id: str, messages_endpoint: str) -> None:
        self.session_id = session_id
        self.messages_endpoint = messages_endpoint
        self.created_at = time.time()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._closed = False

    async def send_event(self, event: str, data: str) -> None:
        """Queue an SSE event for delivery to the client."""
        if not self._closed:
            await self._queue.put(format_sse_event(event, data))

    async def events(self) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted events as they arrive."""
        # Send the endpoint event first (per MCP SSE transport spec)
        yield format_sse_event("endpoint", self.messages_endpoint)

        while not self._closed:
            try:
                event = await asyncio.wait_for(
                    self._queue.get(), timeout=KEEPALIVE_INTERVAL
                )
                yield event
            except asyncio.TimeoutError:
                # Send keepalive ping
                yield format_sse_event("ping", "keepalive")

    def close(self) -> None:
        """Mark this session as closed."""
        self._closed = True


class SSETransport:
    """Manages SSE sessions and routes JSON-RPC messages through them.

    Wraps the existing ``JsonRpcTransport`` to add SSE framing.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SSESession] = {}
        self._jsonrpc = get_transport()

    def create_session(self, session_id: str, messages_endpoint: str) -> SSESession:
        """Create a new SSE session."""
        session = SSESession(session_id, messages_endpoint)
        self._sessions[session_id] = session
        log.info("sse.session_created", session_id=session_id)
        return session

    def get_session(self, session_id: str) -> SSESession | None:
        """Look up an active session."""
        return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> None:
        """Close and remove a session."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.close()
            log.info("sse.session_closed", session_id=session_id)

    async def handle_message(
        self,
        session_id: str,
        raw_json: str,
    ) -> str:
        """Process a JSON-RPC message and push the response via SSE.

        Returns the raw JSON-RPC response string (also queued on the SSE stream).
        """
        session = self._sessions.get(session_id)

        # Process the JSON-RPC request
        response_json = await self._jsonrpc.handle(raw_json)

        # If there's an active SSE session, push the response as an SSE event
        if session and response_json:
            await session.send_event("message", response_json)

        return response_json

    @property
    def active_session_count(self) -> int:
        return len(self._sessions)


# ── Singleton ────────────────────────────────────────────────────────────────

_sse_transport: SSETransport | None = None


def get_sse_transport() -> SSETransport:
    """Return the cached SSE transport singleton."""
    global _sse_transport
    if _sse_transport is None:
        _sse_transport = SSETransport()
    return _sse_transport


def reset_sse_transport() -> None:
    """Reset the singleton (for testing)."""
    global _sse_transport
    _sse_transport = None
