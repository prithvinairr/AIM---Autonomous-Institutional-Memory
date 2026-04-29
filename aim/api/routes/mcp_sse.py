"""MCP SSE transport routes — wires the SSE transport into FastAPI.

Implements two endpoints per the MCP spec:
  - ``GET /mcp/sse``       — initiates an SSE event stream with endpoint discovery
  - ``POST /mcp/messages``  — receives JSON-RPC 2.0 requests for an SSE session

See: https://spec.modelcontextprotocol.io/specification/2024-11-05/basic/transports/#http-with-sse
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from aim.mcp.sse_transport import get_sse_transport

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/mcp", tags=["MCP SSE Transport"])


@router.get("/sse", summary="MCP SSE stream — initiates an SSE event stream")
async def sse_stream(request: Request) -> StreamingResponse:
    """Initiate an SSE connection per the MCP transport specification.

    The server sends an ``endpoint`` event with the messages URL, then
    maintains a keepalive stream with periodic ``ping`` events.
    """
    session_id = str(uuid.uuid4())
    messages_endpoint = f"/mcp/messages?session_id={session_id}"

    transport = get_sse_transport()
    session = transport.create_session(session_id, messages_endpoint)

    log.info("mcp.sse.connection_opened", session_id=session_id)

    async def event_generator():
        try:
            async for event in session.events():
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                yield event
        finally:
            transport.close_session(session_id)
            log.info("mcp.sse.connection_closed", session_id=session_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.post("/messages", summary="MCP JSON-RPC message — dispatch via SSE session")
async def post_message(request: Request, session_id: str) -> Response:
    """Receive a JSON-RPC 2.0 request and dispatch it via the SSE session.

    The response is both returned directly and pushed to the SSE stream.
    If no active SSE session exists, the request is still processed via
    the underlying JSON-RPC transport (graceful degradation).
    """
    transport = get_sse_transport()
    session = transport.get_session(session_id)

    if session is None:
        log.warning("mcp.sse.session_not_found", session_id=session_id)
        # Graceful degradation: still process the request via JSONRPC
        from aim.mcp.jsonrpc import get_transport
        raw = await request.body()
        response_json = await get_transport().handle(raw.decode("utf-8"))
        return Response(
            content=response_json,
            media_type="application/json",
        )

    raw = await request.body()
    response_json = await transport.handle_message(session_id, raw.decode("utf-8"))

    return Response(
        content=response_json,
        media_type="application/json",
    )
