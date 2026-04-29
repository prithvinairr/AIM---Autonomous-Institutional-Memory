"""FastAPI middleware — request ID, latency, Prometheus metrics, security headers, body limit."""
from __future__ import annotations

import re
import time
import uuid
from typing import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from aim.utils.metrics import HTTP_REQUEST_LATENCY, HTTP_REQUEST_TOTAL

log = structlog.get_logger(__name__)

# Regex to collapse UUID and other high-cardinality path segments into
# a fixed placeholder so Prometheus labels stay bounded.
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_HEX_ID_RE = re.compile(r"/[0-9a-fA-F]{16,}/")


def _normalize_path(path: str) -> str:
    """Replace UUIDs and long hex IDs in paths with placeholders.

    ``/api/v1/query/550e8400-e29b-...`` → ``/api/v1/query/{id}``
    """
    path = _UUID_RE.sub("{id}", path)
    path = _HEX_ID_RE.sub("/{id}/", path)
    return path


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with a body larger than ``max_bytes``.

    Prevents denial-of-service via oversized payloads (e.g. massive graph
    ingest requests). Checked early in the middleware stack before any
    JSON parsing or validation occurs.
    """

    def __init__(self, app, max_bytes: int = 2_097_152) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Fast-path: reject immediately if Content-Length exceeds limit
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                cl_int = int(content_length)
            except (ValueError, OverflowError):
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header."},
                )
            if cl_int > self._max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"Request body too large. Maximum size: {self._max_bytes} bytes."
                    },
                )

        # For chunked/streaming requests without Content-Length, read the body
        # and check actual size. Only applies to methods that carry a body.
        if request.method in ("POST", "PUT", "PATCH") and not content_length:
            body = await request.body()
            if len(body) > self._max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"Request body too large. Maximum size: {self._max_bytes} bytes."
                    },
                )

        return await call_next(request)

_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Per-request:
      - Generates / propagates X-Request-ID
      - Binds structlog context vars (cleared after response)
      - Records HTTP metrics in Prometheus
      - Injects security headers on every response
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        t0 = time.perf_counter()
        response: Response | None = None

        try:
            response = await call_next(request)
        except Exception as exc:
            log.error("request.unhandled_error", error=type(exc).__name__)
            raise
        finally:
            latency_s = time.perf_counter() - t0
            latency_ms = round(latency_s * 1000, 1)
            status_code = response.status_code if response is not None else 500

            # Prometheus — skip internal probes; normalize paths to prevent
            # cardinality explosion from UUIDs in parameterized routes.
            if request.url.path not in ("/health", "/metrics", "/ready"):
                metric_path = _normalize_path(request.url.path)
                HTTP_REQUEST_TOTAL.labels(
                    method=request.method,
                    path=metric_path,
                    status_code=str(status_code),
                ).inc()
                HTTP_REQUEST_LATENCY.labels(
                    method=request.method,
                    path=metric_path,
                ).observe(latency_s)

            log.info(
                "request.complete",
                status=status_code,
                latency_ms=latency_ms,
            )
            structlog.contextvars.clear_contextvars()

        # response is guaranteed non-None here — if call_next raised, the
        # except block re-raised and we never reach this point.
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Latency-Ms"] = str(latency_ms)
        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value

        return response
