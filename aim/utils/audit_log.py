"""Audit logger for external API data flows.

Tracks what data was sent to which external API endpoint (LLM, embedding,
vector DB) for compliance and sovereignty auditing.  Entries are stored in
Redis with configurable TTL and exposed via ``/api/v1/audit``.

Each audit entry records:
  - Timestamp and query ID
  - Target provider and model
  - Volume (tokens, entities, snippets)
  - Data classifications that were included
  - Direction (outbound to external API)
"""
from __future__ import annotations

import json
import time
from typing import Any
from uuid import UUID

import structlog

from aim.utils.tenant_keys import DEFAULT_TENANT, tenant_key

log = structlog.get_logger(__name__)

# Legacy (pre-Phase 6) key shapes — kept only so ``get_recent(tenant_id=None)``
# can read entries written before the rollout until their TTL expires.
_AUDIT_PREFIX = "aim:audit:"
_AUDIT_INDEX_KEY = "aim:audit:index"


def _tenant_audit_index(tenant_id: str) -> str:
    """The per-tenant audit sorted-set index — ``aim:{tenant}:audit:index``."""
    return tenant_key("audit", "index", tenant_id=tenant_id)


def _tenant_audit_entry_key(tenant_id: str, query_id: str, endpoint_type: str, timestamp: float) -> str:
    """The per-tenant entry key — ``aim:{tenant}:audit:{qid}:{kind}:{ts}``."""
    return tenant_key("audit", query_id, endpoint_type, str(timestamp), tenant_id=tenant_id)


class AuditEntry:
    """A single audit log entry for an external API call."""

    __slots__ = (
        "timestamp",
        "query_id",
        "direction",
        "provider",
        "model",
        "endpoint_type",
        "data_summary",
        "classifications_sent",
        "api_key_hash",
        "tenant_id",
    )

    def __init__(
        self,
        query_id: str,
        provider: str,
        model: str,
        endpoint_type: str,
        data_summary: dict[str, Any],
        classifications_sent: list[str] | None = None,
        api_key_hash: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        self.timestamp = time.time()
        self.query_id = query_id
        self.direction = "outbound"
        self.provider = provider
        self.model = model
        self.endpoint_type = endpoint_type
        self.data_summary = data_summary
        self.classifications_sent = classifications_sent or []
        self.api_key_hash = api_key_hash or ""
        # First-class field so _store can route the entry to the right
        # per-tenant index without archaeology on data_summary.
        self.tenant_id = tenant_id or DEFAULT_TENANT

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "query_id": self.query_id,
            "direction": self.direction,
            "provider": self.provider,
            "model": self.model,
            "endpoint_type": self.endpoint_type,
            "data_summary": self.data_summary,
            "classifications_sent": self.classifications_sent,
            "api_key_hash": self.api_key_hash,
            "tenant_id": self.tenant_id,
        }


class AuditLogger:
    """Logs data sent to external APIs for compliance auditing.

    Uses Redis for persistent storage with configurable TTL.
    Falls back to structured logging when Redis is unavailable.
    """

    def __init__(self) -> None:
        self._redis = None
        self._ttl: int = 2_592_000  # 30 days default
        self._enabled: bool = True

    async def _get_redis(self):
        """Lazy-load Redis client."""
        if self._redis is not None:
            return self._redis
        try:
            from aim.utils.cache import get_response_cache

            cache = get_response_cache()
            self._redis = cache._redis  # reuse the shared Redis connection
            from aim.config import get_settings
            s = get_settings()
            self._ttl = s.audit_log_ttl_seconds
            self._enabled = s.audit_log_enabled
        except Exception:
            self._redis = None
        return self._redis

    async def log_llm_call(
        self,
        query_id: UUID | str,
        provider: str,
        model: str,
        num_entities: int = 0,
        num_snippets: int = 0,
        num_mcp_items: int = 0,
        classifications_sent: list[str] | None = None,
        estimated_input_tokens: int = 0,
        tenant_id: str | None = None,
        query_excerpt: str | None = None,
        vector_redactions: int = 0,
        mcp_redactions: int = 0,
        field_redactions: int = 0,
        corrective_action: str | None = None,
        api_key_hash: str | None = None,
    ) -> None:
        """Record an outbound LLM inference call.

        Extended fields for sovereignty compliance:
        - ``tenant_id``: identifies the tenant whose data was sent.
        - ``query_excerpt``: first 200 chars of the query for audit traceability.
        - ``vector_redactions`` / ``mcp_redactions`` / ``field_redactions``:
          counts of redactions applied before the LLM dispatch — proves that
          sensitive content was stripped rather than silently forwarded.
        - ``corrective_action``: any action taken by the sovereignty guard
          (e.g. "blocked", "audit_logged", "redacted_fields=[ssn,email]").
        - ``api_key_hash``: SHA-256 hash of the caller's API key for attribution.
        """
        entry = AuditEntry(
            query_id=str(query_id),
            provider=provider,
            model=model,
            endpoint_type="llm_inference",
            data_summary={
                "graph_entities": num_entities,
                "vector_snippets": num_snippets,
                "mcp_items": num_mcp_items,
                "estimated_input_tokens": estimated_input_tokens,
                "tenant_id": tenant_id or DEFAULT_TENANT,
                "query_excerpt": (query_excerpt or "")[:200],
                "vector_redactions": vector_redactions,
                "mcp_redactions": mcp_redactions,
                "field_redactions": field_redactions,
                "corrective_action": corrective_action or "",
            },
            classifications_sent=classifications_sent,
            api_key_hash=api_key_hash,
            tenant_id=tenant_id,
        )
        await self._store(entry)

    async def log_embedding_call(
        self,
        query_id: UUID | str,
        provider: str,
        model: str,
        num_texts: int = 0,
        total_chars: int = 0,
        classifications_sent: list[str] | None = None,
        tenant_id: str | None = None,
        api_key_hash: str | None = None,
    ) -> None:
        """Record an outbound embedding API call.

        ``classifications_sent`` mirrors the field used by ``log_llm_call``
        so the audit stream is uniform — every external dispatch records
        which data classes crossed the boundary regardless of endpoint.
        """
        entry = AuditEntry(
            query_id=str(query_id),
            provider=provider,
            model=model,
            endpoint_type="embedding",
            data_summary={
                "num_texts": num_texts,
                "total_chars": total_chars,
                "tenant_id": tenant_id or DEFAULT_TENANT,
            },
            classifications_sent=classifications_sent,
            api_key_hash=api_key_hash,
            tenant_id=tenant_id,
        )
        await self._store(entry)

    async def _store(self, entry: AuditEntry) -> None:
        """Persist an audit entry to Redis or fall back to structured logging."""
        if not self._enabled:
            return

        entry_dict = entry.to_dict()
        log.info("audit.external_api_call", **entry_dict)

        redis = await self._get_redis()
        if redis is None:
            return

        try:
            # Phase 6: all writes use tenanted keys. Cross-tenant isolation
            # becomes structural — a read with tenant A's index can't
            # surface tenant B's entries because they live in different
            # sorted sets. Legacy ``aim:audit:*`` keys are NOT dual-written;
            # existing entries drain via TTL.
            key = _tenant_audit_entry_key(
                entry.tenant_id, entry.query_id, entry.endpoint_type, entry.timestamp,
            )
            index = _tenant_audit_index(entry.tenant_id)
            await redis.setex(key, self._ttl, json.dumps(entry_dict))
            await redis.zadd(index, {key: entry.timestamp})
            # Trim index entries older than TTL — scoped to this tenant's
            # index only, so tenants can't purge each other's history.
            cutoff = time.time() - self._ttl
            await redis.zremrangebyscore(index, "-inf", cutoff)
        except Exception as exc:
            log.warning("audit.store_failed", error=str(exc))

    async def get_recent(
        self,
        limit: int = 50,
        tenant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve recent audit entries (newest first).

        If ``tenant_id`` is supplied the read is scoped to that tenant's
        per-tenant index (``aim:{tenant}:audit:index``) — other tenants'
        entries are physically unreachable from this call, no
        application-layer filter required.

        If ``tenant_id`` is omitted we fall back to the legacy global
        index (``aim:audit:index``) for back-compat with pre-rollout
        entries and admin tools that don't know their tenant. That
        fallback path expires naturally once the legacy TTL drains.
        """
        redis = await self._get_redis()
        if redis is None:
            return []

        index_key = (
            _tenant_audit_index(tenant_id) if tenant_id else _AUDIT_INDEX_KEY
        )
        try:
            keys = await redis.zrevrange(index_key, 0, limit - 1)
            if not keys:
                return []
            entries = []
            for key in keys:
                raw = await redis.get(key)
                if raw:
                    entries.append(json.loads(raw))
            return entries
        except Exception as exc:
            log.warning("audit.read_failed", error=str(exc))
            return []


# ── Singleton ────────────────────────────────────────────────────────────────

_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Return the singleton AuditLogger."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def reset_audit_logger() -> None:
    """Reset singleton (for testing)."""
    global _audit_logger
    _audit_logger = None
