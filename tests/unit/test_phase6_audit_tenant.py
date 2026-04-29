"""Phase 6 — audit log gets tenanted keys.

The earlier Phase 6 passes (conversations, user_threads, rate_limit, cache,
feedback) shipped structural tenant isolation: every Redis key carries an
``aim:{tenant_id}:...`` prefix so reads can't cross boundaries even if an
application-layer check is missed.

Audit log was deferred because the index is a sorted set rather than a flat
key and it wasn't obvious how to shard it. This test file pins the chosen
design:

* Entry keys move from ``aim:audit:{qid}:{kind}:{ts}`` to
  ``aim:{tenant}:audit:{qid}:{kind}:{ts}``.
* Each tenant gets its own sorted-set index at ``aim:{tenant}:audit:index``;
  there is no global index post-rollout.
* Reads scoped to a tenant see only that tenant's entries; cross-tenant
  leakage is structurally impossible.
* ``get_recent(limit)`` (no tenant) keeps working by reading the legacy
  ``aim:audit:index`` so existing callers and pre-rollout entries stay
  readable until their TTL expires.
* Writes go ONLY to tenanted keys — the legacy index is retired on write,
  consistent with the rest of Phase 6.
"""
from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock

import pytest

from aim.utils.audit_log import AuditEntry, AuditLogger, reset_audit_logger


@pytest.fixture(autouse=True)
def _reset():
    reset_audit_logger()
    yield
    reset_audit_logger()


@pytest.fixture
def logger():
    al = AuditLogger()
    al._enabled = True
    al._ttl = 3600
    return al


def _mock_redis() -> AsyncMock:
    r = AsyncMock()
    r.setex = AsyncMock()
    r.zadd = AsyncMock()
    r.zremrangebyscore = AsyncMock()
    r.zrevrange = AsyncMock(return_value=[])
    r.get = AsyncMock(return_value=None)
    return r


# ── Entry-level shape ───────────────────────────────────────────────────────


class TestAuditEntryTenantField:
    def test_tenant_id_defaults_to_default_sentinel(self):
        entry = AuditEntry(
            query_id="q-1",
            provider="p",
            model="m",
            endpoint_type="e",
            data_summary={},
        )
        # Backwards-compat: constructing an AuditEntry without tenant_id must
        # still work — the rest of the suite relies on the short-form signature.
        assert entry.tenant_id == "default"

    def test_explicit_tenant_id_is_round_tripped_to_dict(self):
        entry = AuditEntry(
            query_id="q-1",
            provider="p",
            model="m",
            endpoint_type="e",
            data_summary={},
            tenant_id="abc123def456",
        )
        d = entry.to_dict()
        assert d["tenant_id"] == "abc123def456"


# ── Write path: tenanted keys ───────────────────────────────────────────────


class TestTenantedWrites:
    @pytest.mark.asyncio
    async def test_llm_call_writes_tenanted_entry_and_index(self, logger):
        r = _mock_redis()
        logger._redis = r

        await logger.log_llm_call(
            query_id="q-alpha",
            provider="anthropic",
            model="claude-3",
            tenant_id="tenantA",
        )

        # Entry key is prefixed with aim:tenantA:audit:
        setex_key = r.setex.call_args[0][0]
        assert setex_key.startswith("aim:tenantA:audit:q-alpha:llm_inference:")

        # Index is the tenanted sorted set.
        zadd_key = r.zadd.call_args[0][0]
        assert zadd_key == "aim:tenantA:audit:index"

        # zadd stores the same entry key as the member.
        mapping = r.zadd.call_args[0][1]
        assert setex_key in mapping

    @pytest.mark.asyncio
    async def test_missing_tenant_id_collapses_to_default(self, logger):
        """Callers that don't know their tenant (legacy code paths, early
        synthesizer calls) must still produce a valid tenanted key — not
        crash and not leak into the legacy unprefixed form."""
        r = _mock_redis()
        logger._redis = r

        await logger.log_llm_call(
            query_id="q-beta",
            provider="anthropic",
            model="claude-3",
        )

        setex_key = r.setex.call_args[0][0]
        assert setex_key.startswith("aim:default:audit:q-beta:")
        zadd_key = r.zadd.call_args[0][0]
        assert zadd_key == "aim:default:audit:index"

    @pytest.mark.asyncio
    async def test_embedding_call_writes_tenanted_entry_and_index(self, logger):
        """Embedding path must shard identically to the LLM path — otherwise
        one endpoint leaks and the other doesn't."""
        r = _mock_redis()
        logger._redis = r

        await logger.log_embedding_call(
            query_id="q-gamma",
            provider="openai",
            model="text-embedding-3-small",
            tenant_id="tenantB",
        )

        setex_key = r.setex.call_args[0][0]
        assert setex_key.startswith("aim:tenantB:audit:q-gamma:embedding:")
        assert r.zadd.call_args[0][0] == "aim:tenantB:audit:index"

    @pytest.mark.asyncio
    async def test_legacy_index_is_not_written(self, logger):
        """Phase 6 contract: never dual-write to the legacy index.  Reads
        fall back, writes don't."""
        r = _mock_redis()
        logger._redis = r

        await logger.log_llm_call(
            query_id="q-delta",
            provider="anthropic",
            model="claude-3",
            tenant_id="tenantC",
        )

        # Only one zadd total, and its key must be the tenanted variant.
        assert r.zadd.call_count == 1
        assert r.zadd.call_args[0][0] == "aim:tenantC:audit:index"

    @pytest.mark.asyncio
    async def test_trim_targets_the_tenant_index(self, logger):
        """Entry trimming (zremrangebyscore) runs against the per-tenant
        index, not the global legacy one — otherwise tenant A's writes
        would be purging tenant B's index too."""
        r = _mock_redis()
        logger._redis = r

        await logger.log_llm_call(
            query_id="q-eps",
            provider="anthropic",
            model="claude-3",
            tenant_id="tenantD",
        )

        assert r.zremrangebyscore.call_count == 1
        assert r.zremrangebyscore.call_args[0][0] == "aim:tenantD:audit:index"


# ── Read path: tenant isolation + legacy fallback ──────────────────────────


class TestTenantedReads:
    @pytest.mark.asyncio
    async def test_get_recent_by_tenant_reads_only_tenant_index(self, logger):
        """A read scoped to tenantA must hit aim:tenantA:audit:index — if
        it hit the legacy global index it would surface other tenants."""
        r = _mock_redis()
        entry = json.dumps({
            "timestamp": time.time(),
            "query_id": "q-1",
            "provider": "anthropic",
            "model": "claude-3",
            "endpoint_type": "llm_inference",
            "direction": "outbound",
            "data_summary": {},
            "classifications_sent": [],
            "tenant_id": "tenantA",
        })
        r.zrevrange = AsyncMock(return_value=["aim:tenantA:audit:q-1:llm_inference:123"])
        r.get = AsyncMock(return_value=entry)
        logger._redis = r

        result = await logger.get_recent(limit=10, tenant_id="tenantA")

        assert r.zrevrange.call_args[0][0] == "aim:tenantA:audit:index"
        assert len(result) == 1
        assert result[0]["tenant_id"] == "tenantA"

    @pytest.mark.asyncio
    async def test_tenant_isolation_no_leakage(self, logger):
        """zrevrange on tenantA's index returns zero entries → the reader
        must surface the empty list, NOT transparently fall through to a
        global index that would leak tenantB's data."""
        r = _mock_redis()
        r.zrevrange = AsyncMock(return_value=[])  # tenantA empty
        logger._redis = r

        result = await logger.get_recent(limit=10, tenant_id="tenantA")
        assert result == []
        # Only one zrevrange call — no fallthrough to global.
        assert r.zrevrange.call_count == 1
        assert r.zrevrange.call_args[0][0] == "aim:tenantA:audit:index"

    @pytest.mark.asyncio
    async def test_legacy_global_read_still_works_during_migration(self, logger):
        """get_recent() without tenant_id keeps reading the legacy global
        index for callers (e.g. admin dashboards, existing tests) that
        haven't been tenantified yet. This preserves back-compat until
        legacy TTL drains."""
        r = _mock_redis()
        entry = json.dumps({
            "timestamp": time.time(),
            "query_id": "q-legacy",
            "provider": "anthropic",
            "model": "claude-3",
            "endpoint_type": "llm_inference",
            "direction": "outbound",
            "data_summary": {},
            "classifications_sent": [],
        })
        r.zrevrange = AsyncMock(return_value=["aim:audit:q-legacy:llm_inference:99"])
        r.get = AsyncMock(return_value=entry)
        logger._redis = r

        result = await logger.get_recent(limit=10)
        assert r.zrevrange.call_args[0][0] == "aim:audit:index"
        assert len(result) == 1
        assert result[0]["query_id"] == "q-legacy"


# ── Cross-tenant leakage regression ────────────────────────────────────────


class TestCrossTenantLeakage:
    @pytest.mark.asyncio
    async def test_tenantA_index_does_not_contain_tenantB_keys(self, logger):
        """End-to-end: write one entry per tenant and ensure the keys
        produced land in distinct sorted sets."""
        r = _mock_redis()
        logger._redis = r

        await logger.log_llm_call(query_id="a", provider="p", model="m", tenant_id="A")
        await logger.log_llm_call(query_id="b", provider="p", model="m", tenant_id="B")

        # Collect every zadd call and bucket by index name.
        by_index: dict[str, list[str]] = {}
        for call in r.zadd.call_args_list:
            index_name = call[0][0]
            mapping = call[0][1]
            by_index.setdefault(index_name, []).extend(mapping.keys())

        assert set(by_index.keys()) == {"aim:A:audit:index", "aim:B:audit:index"}
        # A's index only has A's entry key, and vice versa.
        assert all("q-a" in k or ":a:" in k or k.endswith(":a") or "aim:A:" in k
                   for k in by_index["aim:A:audit:index"])
        assert all("aim:B:" in k for k in by_index["aim:B:audit:index"])
