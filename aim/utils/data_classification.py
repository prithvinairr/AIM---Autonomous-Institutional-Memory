"""Data classification for LLM context boundary enforcement.

Classifies entity properties into four sensitivity levels and filters/redacts
them before they enter the LLM context window.  This prevents sensitive data
(PII, credentials, secrets) from being sent to third-party inference APIs.

Classification levels (ascending sensitivity):
    PUBLIC       — safe for any consumer
    INTERNAL     — organisation-internal, acceptable for most LLM workloads
    CONFIDENTIAL — HR/finance data, only sent when explicitly allowed
    RESTRICTED   — PII, secrets, credentials — NEVER sent to LLM
"""
from __future__ import annotations

import re
from enum import IntEnum
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# ── Classification levels ────────────────────────────────────────────────────

_CLASSIFICATION_RANK = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


class DataClassification(IntEnum):
    """Data sensitivity levels, ordered by sensitivity."""

    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3


# Regex patterns that strongly suggest restricted content when found in values.
_RESTRICTED_VALUE_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),         # SSN
    # API keys: real-world keys (Stripe, OpenAI, AWS, etc.) commonly embed
    # dashes / underscores as internal separators — the charset must include
    # them to catch keys like ``sk-prod-abc123...`` or ``ak_live_987...``.
    re.compile(r"(?:sk|pk|ak|key)[-_][a-zA-Z0-9][a-zA-Z0-9_-]{19,}"),
    re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"),    # Private keys
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),            # GitHub PATs
    re.compile(r"xox[bposa]-[a-zA-Z0-9-]+"),       # Slack tokens
    # JWTs: ``eyJ`` is the base64-encoded leading bytes of ``{"alg":...``
    # so every signed JWT header starts that way. Three dot-joined base64
    # segments catches the header.payload.signature shape even for opaque
    # payloads. Conservative minimum lengths (8/8/8) keep false positives
    # low while still catching realistic tokens.
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
]


class DataClassifier:
    """Classifies and filters entity properties for LLM context injection.

    Parameters
    ----------
    restricted_fields : list[str]
        Property names that are always RESTRICTED (never sent to LLM).
    confidential_fields : list[str]
        Property names that are CONFIDENTIAL.
    max_classification : str
        Maximum classification level allowed in the LLM context window.
        Properties above this level are redacted.
    """

    def __init__(
        self,
        restricted_fields: list[str] | None = None,
        confidential_fields: list[str] | None = None,
        max_classification: str = "internal",
    ) -> None:
        self._restricted = {f.lower() for f in (restricted_fields or [])}
        self._confidential = {f.lower() for f in (confidential_fields or [])}
        self._max_level = DataClassification(_CLASSIFICATION_RANK.get(max_classification, 1))

    def classify_field(self, field_name: str, value: Any = None) -> DataClassification:
        """Classify a single property by its field name and optionally its value."""
        name_lower = field_name.lower()

        # Explicit field-name classification
        if name_lower in self._restricted:
            return DataClassification.RESTRICTED
        if name_lower in self._confidential:
            return DataClassification.CONFIDENTIAL

        # Heuristic field-name patterns
        restricted_patterns = {"password", "secret", "token", "private_key", "ssn", "credential"}
        for pattern in restricted_patterns:
            if pattern in name_lower:
                return DataClassification.RESTRICTED

        confidential_patterns = {"email", "phone", "salary", "address", "dob", "birth"}
        for pattern in confidential_patterns:
            if pattern in name_lower:
                return DataClassification.CONFIDENTIAL

        # Value-based detection (only for string values)
        if isinstance(value, str) and value:
            for regex in _RESTRICTED_VALUE_PATTERNS:
                if regex.search(value):
                    return DataClassification.RESTRICTED

        return DataClassification.INTERNAL

    def filter_for_llm(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Return only properties at or below the max classification level.

        Properties above the threshold are excluded entirely.
        """
        result: dict[str, Any] = {}
        for key, value in properties.items():
            level = self.classify_field(key, value)
            if level <= self._max_level:
                result[key] = value
        return result

    def redact_for_llm(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Return all properties, replacing sensitive values with markers.

        Unlike ``filter_for_llm``, this preserves the key names so the LLM
        knows what fields exist — it just can't see their values.
        """
        result: dict[str, Any] = {}
        for key, value in properties.items():
            level = self.classify_field(key, value)
            if level > self._max_level:
                result[key] = f"[REDACTED:{level.name}]"
            else:
                result[key] = value
        return result

    def classify_properties(self, properties: dict[str, Any]) -> dict[str, DataClassification]:
        """Return a mapping from property name → classification level."""
        return {
            key: self.classify_field(key, value)
            for key, value in properties.items()
        }

    def classify_text(self, text: str) -> set[str]:
        """Scan free-form text and return the set of classification levels detected.

        Used by the sovereignty guard to check LLM message payloads.
        Returns classification level names (e.g. {"RESTRICTED", "INTERNAL"}).

        Two tiers run and their findings are unioned:
          1. Regex patterns (literal SSNs, API keys, PEM blocks, ...).
          2. Optional semantic classifier (paraphrased PII / model-detected
             secrets). Gated behind ``settings.semantic_classifier_enabled``;
             silent + no-op when the backend is unavailable.
        """
        found: set[str] = set()
        if not text:
            return found

        # ── Regex tier ───────────────────────────────────────────────────────
        for regex in _RESTRICTED_VALUE_PATTERNS:
            if regex.search(text):
                found.add("RESTRICTED")
                break

        # ── Semantic tier ────────────────────────────────────────────────────
        # Import locally to avoid a circular import at module load time and to
        # keep this tier optional. ``classify_text_semantic`` never raises.
        from aim.utils.semantic_classifier import get_semantic_classifier

        semantic_findings = get_semantic_classifier().classify_text_semantic(text)
        found |= semantic_findings

        # Already at max level → skip the weaker confidential-marker pass.
        if "RESTRICTED" in found:
            return found

        # Check for confidential-looking field references in serialized data
        confidential_markers = {"email", "phone", "salary", "address", "dob", "birth_date"}
        text_lower = text.lower()
        for marker in confidential_markers:
            if marker in text_lower:
                found.add("CONFIDENTIAL")
                break

        if not found:
            found.add("INTERNAL")

        return found


# ── Singleton ────────────────────────────────────────────────────────────────

_classifier: DataClassifier | None = None


def get_data_classifier() -> DataClassifier:
    """Return the singleton DataClassifier, configured from settings."""
    global _classifier
    if _classifier is not None:
        return _classifier

    from aim.config import get_settings

    settings = get_settings()
    _classifier = DataClassifier(
        restricted_fields=settings.restricted_fields,
        confidential_fields=settings.confidential_fields,
        max_classification=settings.llm_max_data_classification,
    )
    log.info(
        "data_classifier.initialized",
        max_level=settings.llm_max_data_classification,
        restricted_count=len(settings.restricted_fields),
        confidential_count=len(settings.confidential_fields),
    )
    return _classifier


def reset_classifier() -> None:
    """Reset singleton (for testing)."""
    global _classifier
    _classifier = None
