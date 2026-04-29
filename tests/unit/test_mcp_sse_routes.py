"""Tests for the MCP SSE transport routes."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.api.routes.mcp_sse import router


@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestSSERoutes:
    """Test the SSE transport API endpoints."""

    @pytest.mark.skip(reason="TestClient stream blocks indefinitely on infinite generators")
    def test_sse_endpoint_returns_event_stream(self, client):
        """GET /mcp/sse should return text/event-stream content type."""
        # The SSE endpoint is long-lived; we just verify it starts correctly
        with client.stream("GET", "/mcp/sse") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            # Read the first chunk — should be the endpoint event
            first_line = next(resp.iter_lines())
            assert "event: endpoint" in first_line
            resp.close()

    def test_post_messages_no_session(self, client):
        """POST /mcp/messages with unknown session should still process."""
        # Graceful degradation: no active SSE session, but JSON-RPC still works
        request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {},
            "id": 1,
        }
        with patch("aim.api.routes.mcp_sse.get_sse_transport") as mock_transport:
            mock_transport.return_value.get_session.return_value = None
            with patch("aim.mcp.jsonrpc.get_transport") as mock_jsonrpc:
                mock_jsonrpc.return_value.handle = AsyncMock(
                    return_value='{"jsonrpc":"2.0","id":1,"result":{}}'
                )
                resp = client.post(
                    "/mcp/messages?session_id=nonexistent",
                    content=json.dumps(request),
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["jsonrpc"] == "2.0"

    def test_post_messages_with_session(self, client):
        """POST /mcp/messages with active session should dispatch."""
        request = {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
        with patch("aim.api.routes.mcp_sse.get_sse_transport") as mock_transport:
            mock_session = MagicMock()
            mock_transport.return_value.get_session.return_value = mock_session
            mock_transport.return_value.handle_message = AsyncMock(
                return_value='{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}'
            )
            resp = client.post(
                "/mcp/messages?session_id=test-session",
                content=json.dumps(request),
            )
            assert resp.status_code == 200
            mock_transport.return_value.handle_message.assert_called_once()
