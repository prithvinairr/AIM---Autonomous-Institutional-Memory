"""Phase 11 — semantic classification as a second pass after regex.

Regex patterns catch literal SSNs, API keys, PEM blocks — anything written in
its canonical form. They will never see ``"nine eight seven dash six five four
dash ..."`` as an SSN. A semantic tier (Presidio / DeBERTa-style NER) fills
that gap, and its findings are unioned with regex findings in
``DataClassifier.classify_text``.

Design constraints (sovereignty-load-bearing):

* **Never fail open.** If the backend is missing, disabled, or raises at
  inference time, we log once and return the empty set. The regex tier still
  runs — the sovereignty guard sees the literal-pattern findings and can do
  its job even when the semantic tier is dark.
* **Opt-in.** ``settings.semantic_classifier_enabled`` defaults to ``False``
  so the heavy ML dependency is never pulled in for users who don't want it.
* **Thin wrapper.** This module owns availability, logging, and the
  public surface; swapping Presidio for DeBERTa later is one ``_detect`` impl.
"""
from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


class SemanticClassifier:
    """Best-effort PII/secret detection via an ML backend.

    The actual backend integration is deferred — ``_detect`` ships as a no-op
    returning ``set()`` so shipping this module never changes behaviour for
    users who don't install the optional dependency. Tests inject a stub
    ``_detect`` to exercise the union semantics.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        _force_unavailable: bool = False,
    ) -> None:
        self._enabled = enabled
        self._available: bool = False

        if not enabled:
            return

        if _force_unavailable:
            log.warning("sovereignty.semantic_classifier_unavailable", reason="forced")
            return

        try:
            self._init_backend()
        except Exception as exc:  # pragma: no cover — depends on optional dep
            log.warning(
                "sovereignty.semantic_classifier_unavailable",
                error=type(exc).__name__,
                message=str(exc),
            )
            self._available = False

    # ── Backend plumbing (overridable for real integrations) ─────────────────

    def _init_backend(self) -> None:
        """Import and wire up the ML backend. No-op in the default build.

        When a real backend is wired in, this method should set
        ``self._available = True`` and arrange for ``_detect`` to call into it.
        Failure modes (ImportError, OSError loading a model file) should raise
        so the constructor's ``except`` records the unavailability.
        """
        # Default build ships without a backend. Flip ``_available`` off and
        # leave ``_detect`` as the no-op below.
        self._available = False

    def _detect(self, text: str) -> set[str]:
        """Return classification-level names detected in ``text``.

        Override in tests or when wiring a real backend. Returning an empty set
        from the default implementation is the correct behaviour when no
        backend is installed.
        """
        return set()

    # ── Public surface ───────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._available

    @property
    def enabled(self) -> bool:
        return self._enabled

    def classify_text_semantic(self, text: str) -> set[str]:
        """Run the semantic tier on ``text``. Never raises.

        Returns the empty set when disabled, unavailable, or on any runtime
        failure from the backend. Callers union this with regex findings.
        """
        if not text or not self._enabled or not self._available:
            return set()
        try:
            return self._detect(text)
        except Exception as exc:
            log.warning(
                "sovereignty.semantic_classifier_error",
                error=type(exc).__name__,
                message=str(exc),
            )
            return set()


# ── Singleton ────────────────────────────────────────────────────────────────

_instance: SemanticClassifier | None = None


def get_semantic_classifier() -> SemanticClassifier:
    """Return the process-wide semantic classifier, configured from settings."""
    global _instance
    if _instance is not None:
        return _instance

    from aim.config import get_settings

    settings = get_settings()
    _instance = SemanticClassifier(enabled=settings.semantic_classifier_enabled)
    log.info(
        "semantic_classifier.initialized",
        enabled=_instance.enabled,
        available=_instance.available,
    )
    return _instance


def reset_semantic_classifier() -> None:
    """Reset singleton (for testing)."""
    global _instance
    _instance = None
