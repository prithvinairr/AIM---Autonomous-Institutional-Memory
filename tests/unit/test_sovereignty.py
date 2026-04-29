"""Tests for the data sovereignty guard."""
from __future__ import annotations

import pytest

from aim.utils.sovereignty import (
    GuardDecision,
    SovereigntyGuard,
    SovereigntyViolation,
)


@pytest.fixture
def no_local_fallback(monkeypatch):
    """Disable the strict-mode local fallback so blocking behavior is observable.

    Post-Move-2, the default settings route sovereign-violating data to a local
    Ollama endpoint instead of blocking. These tests pin the pure blocking
    contract — the fallback path has its own coverage elsewhere."""
    from aim.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "sovereignty_fallback_to_local", False)
    return s


# ── Mode: off ────────────────────────────────────────────────────────────────

def test_off_mode_always_allows():
    guard = SovereigntyGuard(mode="off")
    messages = [{"role": "user", "content": "SSN: 123-45-6789"}]
    decision = guard.check(messages, provider="anthropic")
    assert decision.allowed is True
    assert decision.reason == "sovereignty_off"


# ── Mode: audit ──────────────────────────────────────────────────────────────

def test_audit_mode_logs_but_allows_violation():
    guard = SovereigntyGuard(
        mode="audit",
        allowed_classifications=["PUBLIC", "INTERNAL"],
        external_providers=["anthropic"],
    )
    messages = [{"role": "user", "content": "SSN: 123-45-6789"}]
    decision = guard.check(messages, provider="anthropic")
    assert decision.allowed is True  # audit mode allows
    assert "RESTRICTED" in decision.classifications_found


def test_audit_mode_allows_clean_data():
    guard = SovereigntyGuard(
        mode="audit",
        allowed_classifications=["PUBLIC", "INTERNAL"],
        external_providers=["anthropic"],
    )
    messages = [{"role": "user", "content": "What services depend on Kafka?"}]
    decision = guard.check(messages, provider="anthropic")
    assert decision.allowed is True


# ── Mode: strict ─────────────────────────────────────────────────────────────

def test_strict_mode_blocks_restricted_data(no_local_fallback):
    guard = SovereigntyGuard(
        mode="strict",
        allowed_classifications=["PUBLIC", "INTERNAL"],
        external_providers=["anthropic"],
    )
    messages = [{"role": "user", "content": "SSN: 123-45-6789"}]
    with pytest.raises(SovereigntyViolation) as exc_info:
        guard.check(messages, provider="anthropic")
    assert "RESTRICTED" in str(exc_info.value)
    assert exc_info.value.provider == "anthropic"


def test_strict_mode_blocks_confidential_data(no_local_fallback):
    guard = SovereigntyGuard(
        mode="strict",
        allowed_classifications=["PUBLIC", "INTERNAL"],
        external_providers=["anthropic"],
    )
    messages = [{"role": "user", "content": "email: user@example.com salary: 150000"}]
    with pytest.raises(SovereigntyViolation):
        guard.check(messages, provider="anthropic")


def test_strict_mode_allows_internal_data():
    guard = SovereigntyGuard(
        mode="strict",
        allowed_classifications=["PUBLIC", "INTERNAL"],
        external_providers=["anthropic"],
    )
    messages = [{"role": "user", "content": "What services depend on Kafka?"}]
    decision = guard.check(messages, provider="anthropic")
    assert decision.allowed is True


def test_strict_mode_allows_confidential_when_configured():
    guard = SovereigntyGuard(
        mode="strict",
        allowed_classifications=["PUBLIC", "INTERNAL", "CONFIDENTIAL"],
        external_providers=["anthropic"],
    )
    messages = [{"role": "user", "content": "email: user@example.com"}]
    decision = guard.check(messages, provider="anthropic")
    assert decision.allowed is True


# ── Local provider bypass ────────────────────────────────────────────────────

def test_local_provider_always_passes_even_with_restricted():
    guard = SovereigntyGuard(
        mode="strict",
        allowed_classifications=["PUBLIC"],
        external_providers=["anthropic", "openai"],
    )
    messages = [{"role": "user", "content": "SSN: 123-45-6789"}]
    decision = guard.check(messages, provider="local")
    assert decision.allowed is True
    assert decision.reason == "local_provider"


def test_local_provider_includes_vllm_ollama():
    guard = SovereigntyGuard(
        mode="strict",
        allowed_classifications=["PUBLIC"],
        external_providers=["anthropic", "openai"],
    )
    messages = [{"role": "user", "content": "SSN: 123-45-6789"}]
    for provider in ["local", "vllm", "ollama"]:
        decision = guard.check(messages, provider=provider)
        assert decision.allowed is True


# ── Edge cases ───────────────────────────────────────────────────────────────

def test_empty_messages():
    guard = SovereigntyGuard(mode="strict", external_providers=["anthropic"])
    decision = guard.check([], provider="anthropic")
    assert decision.allowed is True


def test_empty_content():
    guard = SovereigntyGuard(mode="strict", external_providers=["anthropic"])
    decision = guard.check([{"role": "user", "content": ""}], provider="anthropic")
    assert decision.allowed is True


def test_api_key_detected_as_restricted(no_local_fallback):
    guard = SovereigntyGuard(
        mode="strict",
        allowed_classifications=["PUBLIC", "INTERNAL"],
        external_providers=["anthropic"],
    )
    messages = [{"role": "user", "content": "Token is sk_abcdefghijklmnopqrstuvwxyz"}]
    with pytest.raises(SovereigntyViolation):
        guard.check(messages, provider="anthropic")


def test_github_pat_detected_as_restricted(no_local_fallback):
    guard = SovereigntyGuard(
        mode="strict",
        allowed_classifications=["PUBLIC", "INTERNAL"],
        external_providers=["anthropic"],
    )
    messages = [{"role": "user", "content": "Use ghp_" + "1234567890123456789012345678901234AB"}]
    with pytest.raises(SovereigntyViolation):
        guard.check(messages, provider="anthropic")


# ── Strict-mode local fallback (Move 2 primary behavior) ─────────────────────

def test_strict_mode_reroutes_to_local_by_default():
    """With default settings (llm_base_url set, fallback enabled), strict mode
    does NOT raise — it reroutes to the local provider. This is the post-Move-2
    primary contract: sovereign violations degrade to local inference rather
    than crashing the request."""
    from aim.config import get_settings

    s = get_settings()
    assert s.sovereignty_fallback_to_local is True
    assert s.llm_base_url  # default points at Ollama

    guard = SovereigntyGuard(
        mode="strict",
        allowed_classifications=["PUBLIC", "INTERNAL"],
        external_providers=["anthropic"],
    )
    messages = [{"role": "user", "content": "SSN: 123-45-6789"}]
    decision = guard.check(messages, provider="anthropic")
    assert decision.allowed is True
    assert "rerouted_to_local" in decision.reason
    assert "RESTRICTED" in decision.classifications_found


# ── GuardDecision ────────────────────────────────────────────────────────────

def test_guard_decision_defaults():
    d = GuardDecision(allowed=True, reason="test")
    assert d.classifications_found == set()


def test_sovereignty_violation_message():
    exc = SovereigntyViolation(
        provider="anthropic",
        classifications={"RESTRICTED", "INTERNAL"},
        allowed={"PUBLIC", "INTERNAL"},
    )
    assert "RESTRICTED" in str(exc)
    assert "anthropic" in str(exc)
