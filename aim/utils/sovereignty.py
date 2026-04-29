"""Data sovereignty guard.

Enforces that classified data is not sent to external LLM providers when
the deployment requires strict data residency.

Three modes (``SOVEREIGNTY_MODE`` env var):
  - ``off``    — no enforcement (default, dev mode)
  - ``audit``  — log violations but allow the call
  - ``strict`` — block violations with ``SovereigntyViolation``

The guard inspects the concatenated LLM message text, classifies it using
the existing ``DataClassifier``, and checks whether any classification
exceeds the allowed levels for the given provider.

Integration: wrapped at the LLM factory layer so every ``invoke``/``stream``
call in the codebase is covered with zero per-node changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from aim.utils.data_classification import DataClassification, get_data_classifier

log = structlog.get_logger(__name__)

# Ordering: higher index = more sensitive
_CLASSIFICATION_ORDER = {
    "PUBLIC": 0,
    "INTERNAL": 1,
    "CONFIDENTIAL": 2,
    "RESTRICTED": 3,
}


class SovereigntyViolation(Exception):
    """Raised in strict mode when classified data would be sent to an external provider."""

    def __init__(self, provider: str, classifications: set[str], allowed: set[str]) -> None:
        self.provider = provider
        self.classifications = classifications
        self.allowed = allowed
        blocked = classifications - allowed
        super().__init__(
            f"Sovereignty violation: data classified as {sorted(blocked)} "
            f"cannot be sent to external provider '{provider}'. "
            f"Allowed: {sorted(allowed)}."
        )


@dataclass
class GuardDecision:
    allowed: bool
    reason: str
    classifications_found: set[str] = field(default_factory=set)


class SovereigntyGuard:
    """Policy gate that checks data classification before LLM dispatch."""

    def __init__(
        self,
        mode: str = "off",
        allowed_classifications: list[str] | None = None,
        external_providers: list[str] | None = None,
    ) -> None:
        self._mode = mode
        self._allowed = set(c.upper() for c in (allowed_classifications or ["PUBLIC", "INTERNAL"]))
        self._external = set(p.lower() for p in (external_providers or ["anthropic", "openai"]))
        self._classifier = get_data_classifier()

    def check(
        self,
        messages: list[dict[str, str]],
        provider: str,
    ) -> GuardDecision:
        """Check if the messages can be sent to the given provider.

        Returns a ``GuardDecision``. In strict mode, also raises
        ``SovereigntyViolation`` if the check fails.
        """
        if self._mode == "off":
            return GuardDecision(allowed=True, reason="sovereignty_off")

        # Local providers always pass
        if provider.lower() not in self._external:
            return GuardDecision(allowed=True, reason="local_provider")

        # Scan message content for classified data
        classifications_found: set[str] = set()
        for msg in messages:
            content = msg.get("content", "")
            if not content:
                continue
            # Use the classifier's value-based detection on the text
            detected = self._classifier.classify_text(content)
            classifications_found.update(detected)

        if not classifications_found:
            # No classified data detected — default to INTERNAL
            classifications_found = {"INTERNAL"}

        # Check if all found classifications are within allowed set
        violations = classifications_found - self._allowed
        if not violations:
            return GuardDecision(
                allowed=True,
                reason="classifications_within_policy",
                classifications_found=classifications_found,
            )

        # Violation detected
        decision = GuardDecision(
            allowed=False,
            reason=f"blocked_classifications: {sorted(violations)}",
            classifications_found=classifications_found,
        )

        if self._mode == "audit":
            log.warning(
                "sovereignty.audit_violation",
                provider=provider,
                classifications=sorted(classifications_found),
                violations=sorted(violations),
            )
            decision.allowed = True  # audit mode: log but allow
            return decision

        # strict mode: check if local fallback is enabled before blocking
        from aim.config import get_settings
        settings = get_settings()
        if settings.sovereignty_fallback_to_local and settings.llm_base_url:
            log.warning(
                "sovereignty.strict_fallback_to_local",
                provider=provider,
                classifications=sorted(classifications_found),
                violations=sorted(violations),
                local_url=settings.llm_base_url,
            )
            decision.allowed = True
            decision.reason = f"rerouted_to_local: {sorted(violations)}"
            return decision

        log.error(
            "sovereignty.strict_violation",
            provider=provider,
            classifications=sorted(classifications_found),
            violations=sorted(violations),
        )
        raise SovereigntyViolation(
            provider=provider,
            classifications=classifications_found,
            allowed=self._allowed,
        )


_guard: SovereigntyGuard | None = None


def get_sovereignty_guard() -> SovereigntyGuard:
    """Return the configured SovereigntyGuard (singleton)."""
    global _guard
    if _guard is not None:
        return _guard

    from aim.config import get_settings
    settings = get_settings()
    _guard = SovereigntyGuard(
        mode=settings.sovereignty_mode,
        allowed_classifications=settings.sovereignty_allowed_classifications,
        external_providers=settings.external_llm_providers,
    )
    return _guard


def reset_sovereignty_guard() -> None:
    """Reset singleton (for testing)."""
    global _guard
    _guard = None
