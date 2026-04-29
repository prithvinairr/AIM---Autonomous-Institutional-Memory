"""Unit tests for FastAPI middleware — body-limit and request-context."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from aim.api.middleware import RequestBodyLimitMiddleware, RequestContextMiddleware


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_app(max_bytes: int = 1024) -> Starlette:
    """Build a minimal Starlette app with both middlewares for testing."""

    async def ok(request):
        # Read body to ensure it passes through
        body = await request.body()
        return PlainTextResponse(f"ok:{len(body)}")

    async def boom(request):
        raise RuntimeError("intentional kaboom")

    app = Starlette(
        routes=[
            Route("/ok", ok, methods=["POST", "GET"]),
            Route("/boom", boom, methods=["GET"]),
        ],
    )
    # Order matters: body limit runs first (outer), then request context
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=max_bytes)
    return app


# ── RequestBodyLimitMiddleware ───────────────────────────────────────────────

class TestRequestBodyLimitMiddleware:

    def test_invalid_content_length_returns_400(self):
        """Line 60: Invalid Content-Length header -> 400 response."""
        client = TestClient(_make_app(max_bytes=1024))
        response = client.post(
            "/ok",
            content=b"hello",
            headers={"Content-Length": "not-a-number"},
        )
        assert response.status_code == 400
        assert "Invalid Content-Length" in response.json()["detail"]

    def test_body_exceeds_max_bytes_returns_413(self):
        """Lines 70-72: Body size exceeds max bytes -> 413 response."""
        client = TestClient(_make_app(max_bytes=10))
        response = client.post(
            "/ok",
            content=b"x" * 20,
            headers={"Content-Length": str(20)},
        )
        assert response.status_code == 413
        assert "too large" in response.json()["detail"]

    def test_body_within_limit_passes(self):
        """Sanity check: body within limit is accepted."""
        client = TestClient(_make_app(max_bytes=1024))
        response = client.post(
            "/ok",
            content=b"small",
            headers={"Content-Length": "5"},
        )
        assert response.status_code == 200
        assert response.text == "ok:5"


# ── RequestContextMiddleware ─────────────────────────────────────────────────

class TestRequestContextMiddleware:

    def test_unhandled_exception_is_logged_and_reraised(self):
        """Lines 113-115: Unhandled exception logging in RequestContextMiddleware."""
        client = TestClient(_make_app(), raise_server_exceptions=False)
        response = client.get("/boom")
        # The middleware logs the error and re-raises; Starlette returns 500
        assert response.status_code == 500
