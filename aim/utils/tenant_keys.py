"""Phase 6 — tenant-namespaced Redis key helpers.

Before Phase 6, AIM enforced cross-tenant isolation *after* Redis reads by
comparing ``api_key_hash`` fields on fetched records. That works — but it's
defense-in-depth that leans on every call site remembering to do the check.
This module makes the isolation *structural*: every key is prefixed with the
tenant identifier, so a read with tenant A's key physically can't land on
tenant B's data.

``tenant_id`` derivation:

* For a real API key, we hash with SHA-256 and truncate to 16 hex chars
  (128 bits of entropy, matching the convention already baked into
  ``conversation_store._index_key``).
* For the dev / open-auth path we use the literal ``"default"`` tenant. It
  still gets a prefix (``aim:default:...``) so there's one uniform shape for
  every key written by post-Phase-6 code.

Dual-read migration: call sites that were writing to the legacy unprefixed
form read both keys (new first, legacy fallback) and always write to the new
form. Once the legacy TTL expires across production, the fallback path can
be removed. Use ``legacy_key`` to construct the old-shape key verbatim.
"""
from __future__ import annotations

import hashlib

# Sentinel for the anonymous / no-auth tenant.  Kept as a module constant so
# tests and callers can refer to it without string-typos.
DEFAULT_TENANT = "default"

# 16 hex chars = 64 bits — same width already used by ``conversation_store``
# for its per-key index hash, so migrations don't need two different hashes.
_TENANT_HASH_BYTES = 16


def tenant_id_for(api_key: str | None) -> str:
    """Return the tenant identifier for ``api_key``.

    An empty or ``None`` key collapses to ``DEFAULT_TENANT``. A real key is
    SHA-256 hashed and truncated — deterministic across processes so two
    workers derive the same tenant_id from the same caller.
    """
    if not api_key:
        return DEFAULT_TENANT
    return hashlib.sha256(api_key.encode()).hexdigest()[:_TENANT_HASH_BYTES]


def tenant_key(*parts: str, tenant_id: str) -> str:
    """Compose ``aim:{tenant_id}:{parts...}`` — the canonical post-Phase-6 form.

    ``tenant_id`` is keyword-only so call sites read clearly and we can't
    confuse it with a key segment.
    """
    if not parts:
        raise ValueError("tenant_key requires at least one namespace part")
    return "aim:" + tenant_id + ":" + ":".join(parts)


def legacy_key(*parts: str) -> str:
    """Compose the pre-Phase-6 unprefixed key: ``aim:{parts...}``.

    Exists only so dual-read fallback paths can state the old shape
    explicitly. New code should not write to legacy keys.
    """
    if not parts:
        raise ValueError("legacy_key requires at least one namespace part")
    return "aim:" + ":".join(parts)
