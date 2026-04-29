"""Phase 6 — rate-limit key uses tenant prefix.

Rate-limit Redis keys pre-Phase-6 used ``aim:rl:{sha[:20]}``. Post-Phase-6
they use the canonical ``aim:{tenant_id}:rl`` form. The per-minute sliding
window carries a 60-second TTL so no dual-read migration is needed — any
legacy keys still in Redis at deploy-time self-retire within a minute.

This test locks the new key shape at the call site so accidental regressions
to the legacy form are caught.
"""
from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request

from aim.utils.tenant_keys import tenant_id_for, tenant_key


class TestRateLimitKeyShape:
    def test_tenant_key_matches_expected_form(self):
        """The key fed to Redis must have the form ``aim:{tenant}:rl``."""
        api_key = "sk-prod-abc"
        key = tenant_key("rl", tenant_id=tenant_id_for(api_key))
        assert key.startswith("aim:")
        assert key.endswith(":rl")
        # tenant_id is 16 hex chars by construction.
        tenant = key[len("aim:") : -len(":rl")]
        assert len(tenant) == 16
        assert tenant == hashlib.sha256(api_key.encode()).hexdigest()[:16]

    def test_different_api_keys_produce_different_rl_keys(self):
        k1 = tenant_key("rl", tenant_id=tenant_id_for("sk-alpha"))
        k2 = tenant_key("rl", tenant_id=tenant_id_for("sk-beta"))
        assert k1 != k2

    def test_same_api_key_is_stable_across_calls(self):
        k1 = tenant_key("rl", tenant_id=tenant_id_for("sk-stable"))
        k2 = tenant_key("rl", tenant_id=tenant_id_for("sk-stable"))
        assert k1 == k2

    def test_no_api_key_lands_on_default_tenant(self):
        """Dev-mode (no API key) still gets a structurally-prefixed key so
        the rate-limit code path has one uniform shape."""
        key = tenant_key("rl", tenant_id=tenant_id_for(None))
        assert key == "aim:default:rl"


class TestRateLimiterIntegration:
    @pytest.mark.asyncio
    async def test_limiter_passes_tenant_prefixed_key_to_cache(self):
        """Inject a stub cache and confirm the key fed to
        ``sliding_window_rate_limit`` is the new tenant-prefixed form."""
        from aim.api import deps

        api_key = "integration-test-key"
        expected = tenant_key("rl", tenant_id=tenant_id_for(api_key))

        captured: list[str] = []

        async def fake_swrl(rl_key, rpm, window):
            captured.append(rl_key)
            return (1, rpm)  # allowed, remaining

        fake_cache = type(
            "FakeCache",
            (),
            {"sliding_window_rate_limit": staticmethod(fake_swrl)},
        )()

        # get_response_cache is imported lazily inside _limiter, so patch
        # where it actually resolves (aim.utils.cache).
        from aim.utils import cache as cache_module

        with patch.object(cache_module, "get_response_cache", return_value=fake_cache):
            limiter = deps.make_rate_limiter(requests_per_minute=10)
            await limiter(api_key=api_key)

        assert captured == [expected]
        assert not any(
            k.startswith("aim:rl:") for k in captured
        ), "legacy key shape must not reappear"
