"""Phase 15 — Fernet key rotation.

Pins three contracts:
  1. ``encryption_keys: list[str]`` (newest first) overrides the legacy
     single ``encryption_key`` field.
  2. Encryption always uses the newest key (``keys[0]``).
  3. Decryption tries every configured key in order — so ciphertext written
     under a retired key still reads cleanly during the rotation window.
"""
from __future__ import annotations

import pytest

from aim.utils import encryption as enc


@pytest.fixture(autouse=True)
def _reset_encryption():
    enc.reset_encryption()
    yield
    enc.reset_encryption()


def _fresh_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


# ── (1) Rotation list takes precedence over legacy single key ───────────────


def test_encryption_keys_list_takes_precedence(monkeypatch):
    """When both legacy ``encryption_key`` and new ``encryption_keys`` are set,
    the list wins — ``keys[0]`` is the active encrypt key."""
    from aim.config import get_settings

    new_key = _fresh_key()
    legacy_key = _fresh_key()

    s = get_settings()
    monkeypatch.setattr(s, "encryption_key", legacy_key, raising=False)
    monkeypatch.setattr(s, "encryption_keys", [new_key], raising=False)
    enc.reset_encryption()

    ciphertext = enc.encrypt_value("hello")
    # Prove that decrypting with the new key (not legacy) works.
    from cryptography.fernet import Fernet
    assert Fernet(new_key.encode()).decrypt(ciphertext.encode()).decode() == "hello"


# ── (2) Encrypt uses newest key ─────────────────────────────────────────────


def test_encrypt_uses_newest_key(monkeypatch):
    """``keys[0]`` must be the active encryption key — that's the 'newest first'
    contract the operator relies on during rotation."""
    from aim.config import get_settings

    newest = _fresh_key()
    older = _fresh_key()

    s = get_settings()
    monkeypatch.setattr(s, "encryption_keys", [newest, older], raising=False)
    monkeypatch.setattr(s, "encryption_key", "", raising=False)
    enc.reset_encryption()

    ciphertext = enc.encrypt_value("payload")

    from cryptography.fernet import Fernet, InvalidToken
    # Newest decrypts cleanly
    assert Fernet(newest.encode()).decrypt(ciphertext.encode()).decode() == "payload"
    # Older must NOT decrypt — proves it wasn't used to encrypt
    with pytest.raises(InvalidToken):
        Fernet(older.encode()).decrypt(ciphertext.encode())


# ── (3) Decrypt falls back through retired keys ─────────────────────────────


def test_decrypt_falls_back_to_older_key(monkeypatch):
    """A value encrypted under an older key must still decrypt after rotation,
    as long as the old key is still in ``encryption_keys``. Otherwise rotation
    would orphan every ciphertext in the database."""
    from aim.config import get_settings
    from cryptography.fernet import Fernet

    older = _fresh_key()
    newest = _fresh_key()

    # Step 1: encrypt under the older key directly (simulates data at rest).
    legacy_ciphertext = Fernet(older.encode()).encrypt(b"legacy-secret").decode()

    # Step 2: configure rotation — newest first, older still accepted.
    s = get_settings()
    monkeypatch.setattr(s, "encryption_keys", [newest, older], raising=False)
    monkeypatch.setattr(s, "encryption_key", "", raising=False)
    enc.reset_encryption()

    # Step 3: decrypt via the public API — must succeed by trying the older key.
    assert enc.decrypt_value(legacy_ciphertext) == "legacy-secret"


def test_decrypt_with_no_valid_key_returns_raw(monkeypatch):
    """If ciphertext matches none of the configured keys (e.g. key fully retired),
    fall back to returning the raw value — consistent with existing single-key
    behaviour, so ops don't see hard crashes on partial rotation state."""
    from aim.config import get_settings
    from cryptography.fernet import Fernet

    retired = _fresh_key()
    current = _fresh_key()

    orphan = Fernet(retired.encode()).encrypt(b"orphan").decode()

    s = get_settings()
    monkeypatch.setattr(s, "encryption_keys", [current], raising=False)
    monkeypatch.setattr(s, "encryption_key", "", raising=False)
    enc.reset_encryption()

    # Doesn't crash — returns the raw ciphertext (same contract as legacy
    # "looks like plaintext, return as-is").
    assert enc.decrypt_value(orphan) == orphan


# ── Backwards compat: single-key path still works ──────────────────────────


def test_legacy_single_key_still_works(monkeypatch):
    """Deployments that only set ``encryption_key`` keep working unchanged."""
    from aim.config import get_settings

    s = get_settings()
    key = _fresh_key()
    monkeypatch.setattr(s, "encryption_key", key, raising=False)
    monkeypatch.setattr(s, "encryption_keys", [], raising=False)
    enc.reset_encryption()

    ct = enc.encrypt_value("sensitive")
    assert enc.decrypt_value(ct) == "sensitive"
