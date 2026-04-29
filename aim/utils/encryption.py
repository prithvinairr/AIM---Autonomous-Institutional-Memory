"""Field-level encryption for sensitive graph entity properties.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).

Two configuration shapes are supported:

  * ``Settings.encryption_keys`` — list, newest first. Encryption uses
    ``keys[0]``; decryption tries every key in order.  This is the
    rotation-safe path.
  * ``Settings.encryption_key`` — legacy single-key field.  Used only when
    ``encryption_keys`` is empty.

When both are empty, encrypt/decrypt are no-ops (development mode).

Typical flow:
  1. Before Neo4j write: ``encrypt_fields(properties, encrypted_fields)``
  2. After Neo4j read:   ``decrypt_fields(properties, encrypted_fields)``
"""
from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)

# Lazy state: list of Fernet instances, newest first.  ``[0]`` is the active
# encrypt key; decryption walks the list.  ``None`` means encryption disabled.
_fernets: list | None = None
_INIT_DONE = False


def _get_fernets() -> list | None:
    """Return cached Fernet instances (newest first) or None when disabled."""
    global _fernets, _INIT_DONE
    if _INIT_DONE:
        return _fernets

    from aim.config import get_settings

    settings = get_settings()

    # Prefer the rotation list; fall back to the legacy single key.
    raw_keys: list[str] = [k for k in (settings.encryption_keys or []) if k]
    if not raw_keys and settings.encryption_key:
        raw_keys = [settings.encryption_key]

    if not raw_keys:
        log.debug("encryption.disabled", reason="no encryption key configured")
        _INIT_DONE = True
        _fernets = None
        return None

    try:
        from cryptography.fernet import Fernet

        instances = []
        for k in raw_keys:
            instances.append(Fernet(k.encode() if isinstance(k, str) else k))
        _fernets = instances
        _INIT_DONE = True
        log.info(
            "encryption.enabled",
            fields=settings.encrypted_fields,
            key_count=len(instances),
            rotation=len(instances) > 1,
        )
    except Exception as exc:
        log.error("encryption.init_failed", error=str(exc))
        _INIT_DONE = True
        _fernets = None

    return _fernets


def reset_encryption() -> None:
    """Reset the cached Fernet instances (for testing)."""
    global _fernets, _INIT_DONE
    _fernets = None
    _INIT_DONE = False


# ── Public API ───────────────────────────────────────────────────────────────


def encrypt_value(value: str) -> str:
    """Encrypt a single string value using the newest configured key.

    When encryption is disabled (no key), returns the value unchanged.
    """
    fernets = _get_fernets()
    if not fernets:
        return value
    return fernets[0].encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(value: str) -> str:
    """Decrypt a single Fernet-encrypted string.

    Tries every configured key in order (newest first) so ciphertext written
    under a retiring key still reads during the rotation window.  When every
    key fails, falls back to returning the raw value — consistent with the
    pre-rotation "looks like plaintext, return as-is" contract used when
    encryption was first enabled on existing data.
    """
    fernets = _get_fernets()
    if not fernets:
        return value

    from cryptography.fernet import InvalidToken

    token = value.encode("utf-8")
    for f in fernets:
        try:
            return f.decrypt(token).decode("utf-8")
        except InvalidToken:
            continue
        except Exception:
            # Corrupt / non-base64 input — treat as plaintext.
            log.debug(
                "encryption.decrypt_fallback",
                value_prefix=value[:20] if value else "",
            )
            return value

    # No configured key matched the ciphertext.
    log.debug(
        "encryption.decrypt_no_key_match",
        value_prefix=value[:20] if value else "",
        tried_keys=len(fernets),
    )
    return value


def encrypt_fields(
    properties: dict[str, Any],
    encrypted_fields: list[str],
) -> dict[str, Any]:
    """Return a copy of ``properties`` with specified fields encrypted.

    Only string values are encrypted; non-string values are left unchanged.
    Fields not present in ``properties`` are silently skipped.
    """
    fernets = _get_fernets()
    if not fernets or not encrypted_fields:
        return properties

    result = dict(properties)
    for field in encrypted_fields:
        if field in result and isinstance(result[field], str):
            result[field] = encrypt_value(result[field])
    return result


def decrypt_fields(
    properties: dict[str, Any],
    encrypted_fields: list[str],
) -> dict[str, Any]:
    """Return a copy of ``properties`` with specified fields decrypted.

    Only string values are decrypted; non-string values are left unchanged.
    Fields not present in ``properties`` are silently skipped.
    """
    fernets = _get_fernets()
    if not fernets or not encrypted_fields:
        return properties

    result = dict(properties)
    for field in encrypted_fields:
        if field in result and isinstance(result[field], str):
            result[field] = decrypt_value(result[field])
    return result
