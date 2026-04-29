"""Phase 6 — tenant-namespaced Redis keys (pilot).

Scoped to the helper module + the ``user_threads`` index as a pattern-setting
vertical slice. Cross-tenant isolation was already enforced post-fetch via
``api_key_hash`` equality checks; the tenant prefix makes it *structural* —
no cross-tenant key collisions are possible even if future code forgets the
equality check.

Contract pinned here:

* ``tenant_id_for`` returns a truncated SHA hash for real api_keys and the
  literal ``"default"`` when no key is present.
* ``tenant_key`` composes stable keys of the form ``aim:{tenant}:{...parts}``.
* ``legacy_key`` returns the pre-Phase-6 unprefixed key for dual-read paths.
* The helpers are pure — no Redis needed for the unit tests.
"""
from __future__ import annotations

import hashlib

from aim.utils.tenant_keys import (
    DEFAULT_TENANT,
    legacy_key,
    tenant_id_for,
    tenant_key,
)


class TestTenantIdFor:
    def test_real_api_key_hashes_to_stable_id(self):
        tid_a = tenant_id_for("sk-test-abc123")
        tid_b = tenant_id_for("sk-test-abc123")
        assert tid_a == tid_b
        assert tid_a != "default"
        # Matches the 16-char truncation convention already used in
        # conversation_store._index_key so the same tenant_id plays nicely
        # with existing per-hash indexing.
        expected = hashlib.sha256(b"sk-test-abc123").hexdigest()[:16]
        assert tid_a == expected

    def test_distinct_keys_yield_distinct_ids(self):
        assert tenant_id_for("sk-alpha") != tenant_id_for("sk-beta")

    def test_none_falls_back_to_default(self):
        assert tenant_id_for(None) == DEFAULT_TENANT
        assert DEFAULT_TENANT == "default"

    def test_empty_string_falls_back_to_default(self):
        """An empty key string is semantically the same as no key — the dev
        path. Don't fingerprint the empty string into a real tenant."""
        assert tenant_id_for("") == DEFAULT_TENANT


class TestTenantKey:
    def test_single_namespace(self):
        tid = tenant_id_for("sk-x")
        assert tenant_key("user_threads", tenant_id=tid) == f"aim:{tid}:user_threads"

    def test_multiple_parts_are_colon_joined(self):
        tid = "t1"
        assert tenant_key("conv", "abc-123", tenant_id=tid) == "aim:t1:conv:abc-123"

    def test_default_tenant_still_gets_prefix(self):
        """Even the 'default' tenant keys go under ``aim:default:...``. This
        is the structural guarantee — no unprefixed writes from new code."""
        assert (
            tenant_key("rl", "hash123", tenant_id=DEFAULT_TENANT)
            == "aim:default:rl:hash123"
        )

    def test_tenant_id_required_kwonly(self):
        """Positional tenant_id would be ambiguous with a key part. Force
        keyword usage so call sites read clearly."""
        import pytest

        with pytest.raises(TypeError):
            tenant_key("conv", "abc", "t1")  # type: ignore[call-arg]


class TestLegacyKey:
    def test_matches_pre_phase6_form(self):
        """The legacy key must be byte-identical to what the store wrote
        before Phase 6 — otherwise dual-read migration won't find anything."""
        h = hashlib.sha256(b"sk-test").hexdigest()[:16]
        assert legacy_key("user_threads", h) == f"aim:user_threads:{h}"

    def test_accepts_multiple_parts(self):
        assert legacy_key("conv", "thread-id") == "aim:conv:thread-id"

    def test_legacy_and_tenant_forms_differ(self):
        """Same logical identifier produces different byte strings under the
        legacy vs tenant-prefixed forms — this is what makes dual-read
        migration observable."""
        tid = "tenant-abc"
        legacy = legacy_key("user_threads", tid)
        tenanted = tenant_key("user_threads", tenant_id=tid)
        assert legacy != tenanted
