"""Phase 11 — Semantic classification second pass.

Regex catches literal PII/secrets. A paraphrased leak ("nine eight seven dash
six five four dash...") slips right through. The semantic classifier runs
*after* regex as a second pass; findings from either path union into the
final classification set.

Contract pinned here:
    - ``classify_text`` returns RESTRICTED when either regex OR semantic flags it.
    - When the semantic backend is unavailable, we log once and fall back to
      regex-only — never raise. Sovereignty must not fail open on an import error.
    - A disabled backend (feature flag off) is indistinguishable from an
      unavailable one to callers: both return empty semantic findings.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from aim.utils import data_classification, semantic_classifier
from aim.utils.data_classification import DataClassifier, reset_classifier


@pytest.fixture(autouse=True)
def _reset():
    reset_classifier()
    semantic_classifier.reset_semantic_classifier()
    yield
    reset_classifier()
    semantic_classifier.reset_semantic_classifier()


class TestSemanticClassifierBackend:
    def test_unavailable_backend_returns_empty_findings(self):
        """When Presidio/DeBERTa can't be imported, classify_text_semantic must
        return an empty set — callers fall back to regex output cleanly."""
        clf = semantic_classifier.SemanticClassifier(enabled=True, _force_unavailable=True)
        assert clf.classify_text_semantic("the user's SSN is encoded here") == set()
        # The classifier records the unavailability so we can assert logging-free
        # fallback from tests without monkeypatching structlog.
        assert clf.available is False

    def test_disabled_backend_returns_empty_findings(self):
        clf = semantic_classifier.SemanticClassifier(enabled=False)
        assert clf.classify_text_semantic("anything at all") == set()

    def test_available_backend_returns_restricted(self):
        """With a stub backend wired in, paraphrased PII returns RESTRICTED."""
        clf = semantic_classifier.SemanticClassifier(enabled=True)

        def fake_detect(text: str) -> set[str]:
            if "ssn" in text.lower() or "social" in text.lower():
                return {"RESTRICTED"}
            return set()

        clf._detect = fake_detect  # direct stub — backend integration is separate
        clf._available = True

        assert clf.classify_text_semantic("their social is nine eight seven") == {"RESTRICTED"}
        assert clf.classify_text_semantic("completely benign text") == set()


class TestHybridUnion:
    def test_regex_hit_only(self):
        """Regex finds an API key; semantic classifier is silent → RESTRICTED."""
        clf = DataClassifier(max_classification="internal")
        with patch.object(
            semantic_classifier, "get_semantic_classifier"
        ) as get_sc:
            stub = semantic_classifier.SemanticClassifier(enabled=True)
            stub._detect = lambda _text: set()
            stub._available = True
            get_sc.return_value = stub
            found = clf.classify_text("my key is sk-prod-" + "abcdefghijklmnopqrst12345")
        assert "RESTRICTED" in found

    def test_semantic_hit_only(self):
        """Regex misses the paraphrased form; semantic catches it → RESTRICTED.

        This is the whole point of Phase 11 — the regex tier will never see
        'nine eight seven dash six five four' as an SSN."""
        clf = DataClassifier(max_classification="internal")
        with patch.object(
            semantic_classifier, "get_semantic_classifier"
        ) as get_sc:
            stub = semantic_classifier.SemanticClassifier(enabled=True)
            stub._detect = lambda text: (
                {"RESTRICTED"} if "nine eight seven" in text else set()
            )
            stub._available = True
            get_sc.return_value = stub
            found = clf.classify_text(
                "the account holder's tax id is nine eight seven dash six five four"
            )
        assert "RESTRICTED" in found

    def test_neither_hits_returns_internal(self):
        clf = DataClassifier(max_classification="internal")
        with patch.object(
            semantic_classifier, "get_semantic_classifier"
        ) as get_sc:
            stub = semantic_classifier.SemanticClassifier(enabled=True)
            stub._detect = lambda _text: set()
            stub._available = True
            get_sc.return_value = stub
            found = clf.classify_text("today we shipped the new homepage")
        assert found == {"INTERNAL"}

    def test_semantic_unavailable_does_not_fail_open(self):
        """The most important invariant: if the semantic tier breaks, we still
        run regex and return its findings — never an empty set via crash path."""
        clf = DataClassifier(max_classification="internal")
        with patch.object(
            semantic_classifier, "get_semantic_classifier"
        ) as get_sc:
            stub = semantic_classifier.SemanticClassifier(
                enabled=True, _force_unavailable=True
            )
            get_sc.return_value = stub
            # Regex still catches the literal key.
            found = clf.classify_text("sk-prod-" + "abcdefghijklmnopqrst12345")
        assert "RESTRICTED" in found

    def test_semantic_raises_is_caught(self):
        """A runtime error from the backend must not propagate to callers."""
        clf = DataClassifier(max_classification="internal")
        with patch.object(
            semantic_classifier, "get_semantic_classifier"
        ) as get_sc:
            stub = semantic_classifier.SemanticClassifier(enabled=True)

            def _boom(_text):
                raise RuntimeError("backend crashed mid-inference")

            stub._detect = _boom
            stub._available = True
            get_sc.return_value = stub
            # Regex finds nothing, semantic crashes — falls through to INTERNAL.
            found = clf.classify_text("a totally innocuous sentence")
        assert found == {"INTERNAL"}


class TestSingletonWiring:
    def test_get_semantic_classifier_is_memoised(self):
        a = semantic_classifier.get_semantic_classifier()
        b = semantic_classifier.get_semantic_classifier()
        assert a is b

    def test_reset_clears_singleton(self):
        a = semantic_classifier.get_semantic_classifier()
        semantic_classifier.reset_semantic_classifier()
        b = semantic_classifier.get_semantic_classifier()
        assert a is not b


class TestEmptyText:
    def test_empty_string_short_circuits(self):
        clf = DataClassifier(max_classification="internal")
        assert clf.classify_text("") == set()
