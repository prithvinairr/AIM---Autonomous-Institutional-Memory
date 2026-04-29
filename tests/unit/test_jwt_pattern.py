"""Sovereignty hardening — JWT detection in classify_text.

A bare JWT in an LLM prompt is a credential leak: it authenticates the caller
to whatever service issued it. The regex family in ``data_classification``
already catches raw API keys and private keys; this test pins JWT coverage.
"""
from __future__ import annotations

from aim.utils.data_classification import DataClassifier


class TestJWTDetection:
    def test_classic_jwt_is_restricted(self):
        """A realistic 3-segment JWT must be flagged RESTRICTED."""
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0"
            ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        clf = DataClassifier(max_classification="internal")
        found = clf.classify_text(f"here is the session token: {jwt}")
        assert "RESTRICTED" in found

    def test_jwt_embedded_in_sentence(self):
        """The regex must anchor mid-string, not only at the boundary."""
        jwt = "eyJhbGciOiAibm9uZSJ9.eyJoZWxsbyI6InN1biJ9.abcdefghij"
        clf = DataClassifier(max_classification="internal")
        found = clf.classify_text(
            f"The user's authorization header was 'Bearer {jwt}' at request time."
        )
        assert "RESTRICTED" in found

    def test_non_jwt_base64_triplet_is_not_flagged(self):
        """Random dot-separated base64 strings without the ``eyJ`` header
        must not be mistaken for a JWT — the anchor matters."""
        noise = "abcdefghijkl.mnopqrstuvwx.yzABCDEFGHIJ"
        clf = DataClassifier(max_classification="internal")
        found = clf.classify_text(f"random token: {noise}")
        assert "RESTRICTED" not in found

    def test_short_jwt_like_string_is_ignored(self):
        """An ``eyJ`` prefix followed by very short segments (< 8 chars each)
        is almost certainly not a real token — ignore to reduce noise."""
        short = "eyJ.a.b"
        clf = DataClassifier(max_classification="internal")
        found = clf.classify_text(f"example: {short}")
        assert "RESTRICTED" not in found
