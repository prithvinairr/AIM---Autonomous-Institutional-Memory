"""Prometheus metrics for AIM.

All metrics are module-level singletons — safe to import anywhere.
Exposed via GET /metrics (added in main.py).
"""
from __future__ import annotations

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    REGISTRY,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# ── Query-level ───────────────────────────────────────────────────────────────

QUERY_TOTAL = Counter(
    "aim_queries_total",
    "Total queries processed",
    ["status", "depth"],
)

QUERY_LATENCY = Histogram(
    "aim_query_duration_seconds",
    "End-to-end query latency",
    ["depth"],
    buckets=[0.5, 1, 2, 5, 10, 20, 30, 60],
)

SOURCES_PER_QUERY = Histogram(
    "aim_sources_per_query",
    "Number of sources retrieved per query",
    buckets=[0, 1, 5, 10, 20, 50, 100],
)

ANSWER_LENGTH = Histogram(
    "aim_answer_length_chars",
    "Length of synthesized answer in characters",
    buckets=[100, 500, 1000, 2000, 5000, 10000],
)

CONFIDENCE_SCORE = Histogram(
    "aim_confidence_score",
    "Overall provenance confidence score",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# ── Node-level ────────────────────────────────────────────────────────────────

NODE_LATENCY = Histogram(
    "aim_node_duration_seconds",
    "Latency of each LangGraph node",
    ["node_name"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 15, 30],
)

NODE_ERRORS = Counter(
    "aim_node_errors_total",
    "Errors per LangGraph node",
    ["node_name", "error_type"],
)

# ── Data layer ────────────────────────────────────────────────────────────────

NEO4J_QUERY_LATENCY = Histogram(
    "aim_neo4j_query_seconds",
    "Neo4j query latency",
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5],
)

NEO4J_RESULTS = Histogram(
    "aim_neo4j_results_per_query",
    "Neo4j entities returned per search",
    buckets=[0, 1, 5, 10, 20, 50],
)

PINECONE_QUERY_LATENCY = Histogram(
    "aim_pinecone_query_seconds",
    "Pinecone similarity search latency",
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2],
)

EMBEDDING_LATENCY = Histogram(
    "aim_embedding_duration_seconds",
    "OpenAI embedding call latency",
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2],
)

EMBEDDING_CACHE_HITS = Counter(
    "aim_embedding_cache_hits_total",
    "Embedding cache hits",
    ["result"],  # "hit" | "miss"
)

MCP_FETCH_LATENCY = Histogram(
    "aim_mcp_fetch_seconds",
    "MCP provider fetch latency",
    ["provider"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 15],
)

MCP_ITEMS_FETCHED = Counter(
    "aim_mcp_items_total",
    "Total MCP items fetched",
    ["provider"],
)

# ── Token usage & cost ────────────────────────────────────────────────────────

TOKEN_INPUT_TOTAL = Counter(
    "aim_token_input_total",
    "Total LLM input tokens consumed",
    ["model"],
)

TOKEN_OUTPUT_TOTAL = Counter(
    "aim_token_output_total",
    "Total LLM output tokens consumed",
    ["model"],
)

TOKEN_EMBEDDING_TOTAL = Counter(
    "aim_token_embedding_total",
    "Total embedding tokens consumed",
    ["model"],
)

COST_USD_TOTAL = Counter(
    "aim_cost_usd_total",
    "Estimated USD cost of API calls (approximate list pricing)",
    ["component"],  # "llm" | "embedding"
)

# ── Evaluation & reasoning loop ──────────────────────────────────────────────

EVALUATION_SCORE = Histogram(
    "aim_evaluation_score",
    "Heuristic evaluation score after synthesis",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

RELOOP_TOTAL = Counter(
    "aim_reloop_total",
    "Number of times the reasoning loop re-searched due to low evaluation",
)

# ── Conversation ──────────────────────────────────────────────────────────────

CONVERSATION_TURNS = Histogram(
    "aim_conversation_turns",
    "Number of prior turns in context when a query is processed",
    buckets=[0, 1, 2, 5, 10, 20],
)

CONVERSATION_HISTORY_TOKENS = Histogram(
    "aim_conversation_history_messages",
    "Number of history messages injected into LLM context",
    buckets=[0, 2, 4, 8, 12, 16, 20],
)

# ── Ingest worker ────────────────────────────────────────────────────────────

INGEST_QUEUE_DEPTH = Gauge(
    "aim_ingest_queue_depth",
    "Current number of jobs waiting in the ingest queue",
)

INGEST_JOBS_TOTAL = Counter(
    "aim_ingest_jobs_total",
    "Total ingest jobs processed",
    ["status"],  # "done" | "failed" | "retried"
)

# ── Feedback ──────────────────────────────────────────────────────────────────

FEEDBACK_TOTAL = Counter(
    "aim_feedback_total",
    "User feedback submissions by rating",
    ["rating"],  # "positive" | "negative" | "neutral"
)

# ── Circuit breakers ──────────────────────────────────────────────────────────

CIRCUIT_STATE = Gauge(
    "aim_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["service"],
)

CIRCUIT_TRIPS = Counter(
    "aim_circuit_breaker_trips_total",
    "Number of times each circuit opened",
    ["service"],
)

# ── Cache ─────────────────────────────────────────────────────────────────────

CACHE_OPS = Counter(
    "aim_cache_operations_total",
    "Cache get/set operations",
    ["operation", "result"],  # result: "hit" | "miss" | "ok"
)

CACHE_BACKEND = Gauge(
    "aim_cache_backend_info",
    "Active cache backend (1=redis, 0=memory)",
)

# ── HTTP ──────────────────────────────────────────────────────────────────────

HTTP_REQUEST_TOTAL = Counter(
    "aim_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_LATENCY = Histogram(
    "aim_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30],
)

# ── App info ──────────────────────────────────────────────────────────────────

APP_INFO = Info("aim_app", "AIM application metadata")


def init_app_info() -> None:
    from aim.config import get_settings

    s = get_settings()
    APP_INFO.info({"version": s.app_version, "env": s.app_env, "model": s.llm_model})


def update_circuit_metrics() -> None:
    """Call periodically to keep Prometheus circuit-breaker gauges current."""
    from aim.utils.circuit_breaker import all_statuses, CircuitState

    state_to_int = {
        CircuitState.CLOSED: 0,
        CircuitState.HALF_OPEN: 1,
        CircuitState.OPEN: 2,
    }
    for status in all_statuses():
        val = state_to_int.get(status["state"], 0)
        CIRCUIT_STATE.labels(service=status["name"]).set(val)


def prometheus_response() -> tuple[bytes, str]:
    """Return (body, content_type) for the /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
