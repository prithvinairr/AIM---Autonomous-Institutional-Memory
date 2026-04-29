"""OpenTelemetry distributed tracing setup.

Instruments FastAPI, HTTPX, and provides a tracer for manual spans.
Exports via OTLP (Jaeger / Tempo / Datadog Agent) when OTLP_ENDPOINT is set.
Falls back to a no-op tracer if not configured — zero overhead in dev.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from fastapi import FastAPI

log = structlog.get_logger(__name__)

_tracer_provider_initialized = False


def setup_tracing(app: "FastAPI") -> None:
    """Wire OTel into the FastAPI app. Called once from lifespan."""
    global _tracer_provider_initialized
    if _tracer_provider_initialized:
        return

    from aim.config import get_settings

    settings = get_settings()

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        resource = Resource.create(
            {
                SERVICE_NAME: "aim",
                SERVICE_VERSION: settings.app_version,
                "deployment.environment": settings.app_env,
            }
        )
        provider = TracerProvider(resource=resource)

        if settings.otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            log.info("tracing.otlp_enabled", endpoint=settings.otlp_endpoint)
        else:
            log.info("tracing.no_op_mode", hint="Set OTLP_ENDPOINT to enable export")

        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=provider,
            excluded_urls="/health,/metrics",
        )
        HTTPXClientInstrumentor().instrument(tracer_provider=provider)

        _tracer_provider_initialized = True
        log.info("tracing.setup_complete")

    except ImportError as exc:
        log.warning("tracing.disabled", reason=str(exc))


def get_tracer(name: str = "aim"):
    """Return the OTel tracer for manual span creation."""
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


class _NoOpTracer:
    """Fallback when opentelemetry is not installed."""

    def start_as_current_span(self, name: str, **_: object):  # type: ignore[override]
        from contextlib import nullcontext

        return nullcontext()
