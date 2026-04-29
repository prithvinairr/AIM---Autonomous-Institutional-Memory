"""Tests for security features: hash_api_key, body limit middleware."""
from __future__ import annotations

import pytest

from aim.api.deps import hash_api_key


# ── hash_api_key ─────────────────────────────────────────────────────────────

def test_hash_api_key_deterministic():
    """Same key always produces same hash."""
    assert hash_api_key("test-key") == hash_api_key("test-key")


def test_hash_api_key_different_keys_different_hashes():
    """Different keys produce different hashes."""
    assert hash_api_key("key-a") != hash_api_key("key-b")


def test_hash_api_key_same_prefix_different_hashes():
    """Keys sharing a prefix produce different hashes (unlike old 8-char approach)."""
    h1 = hash_api_key("abcdefgh-suffix-one")
    h2 = hash_api_key("abcdefgh-suffix-two")
    assert h1 != h2


def test_hash_api_key_length():
    """Hash is 32 hex chars = 128 bits."""
    h = hash_api_key("any-key")
    assert len(h) == 32
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_api_key_empty_string():
    """Empty string still produces a valid hash."""
    h = hash_api_key("")
    assert len(h) == 32
