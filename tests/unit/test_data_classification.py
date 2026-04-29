"""Tests for aim.utils.data_classification — data sensitivity classification and filtering."""
from __future__ import annotations

import pytest

from aim.utils.data_classification import (
    DataClassification,
    DataClassifier,
    get_data_classifier,
    reset_classifier,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_classifier()
    yield
    reset_classifier()


# ── DataClassification enum ──────────────────────────────────────────────────

class TestDataClassification:
    def test_ordering(self):
        assert DataClassification.PUBLIC < DataClassification.INTERNAL
        assert DataClassification.INTERNAL < DataClassification.CONFIDENTIAL
        assert DataClassification.CONFIDENTIAL < DataClassification.RESTRICTED

    def test_int_values(self):
        assert int(DataClassification.PUBLIC) == 0
        assert int(DataClassification.RESTRICTED) == 3


# ── DataClassifier — classify_field ──────────────────────────────────────────

class TestClassifyField:
    @pytest.fixture
    def classifier(self):
        return DataClassifier(
            restricted_fields=["ssn", "api_token", "password"],
            confidential_fields=["email", "phone", "salary"],
            max_classification="internal",
        )

    def test_explicit_restricted_field(self, classifier):
        assert classifier.classify_field("ssn") == DataClassification.RESTRICTED
        assert classifier.classify_field("api_token") == DataClassification.RESTRICTED
        assert classifier.classify_field("password") == DataClassification.RESTRICTED

    def test_explicit_confidential_field(self, classifier):
        assert classifier.classify_field("email") == DataClassification.CONFIDENTIAL
        assert classifier.classify_field("phone") == DataClassification.CONFIDENTIAL
        assert classifier.classify_field("salary") == DataClassification.CONFIDENTIAL

    def test_case_insensitive(self, classifier):
        assert classifier.classify_field("SSN") == DataClassification.RESTRICTED
        assert classifier.classify_field("Email") == DataClassification.CONFIDENTIAL

    def test_heuristic_restricted_patterns(self, classifier):
        """Field names containing known restricted keywords are auto-classified."""
        assert classifier.classify_field("user_password_hash") == DataClassification.RESTRICTED
        assert classifier.classify_field("slack_token") == DataClassification.RESTRICTED
        assert classifier.classify_field("credential_id") == DataClassification.RESTRICTED
        assert classifier.classify_field("private_key_pem") == DataClassification.RESTRICTED

    def test_heuristic_confidential_patterns(self, classifier):
        assert classifier.classify_field("email_address") == DataClassification.CONFIDENTIAL
        assert classifier.classify_field("phone_number") == DataClassification.CONFIDENTIAL
        assert classifier.classify_field("home_address") == DataClassification.CONFIDENTIAL
        assert classifier.classify_field("date_of_birth") == DataClassification.CONFIDENTIAL

    def test_internal_by_default(self, classifier):
        assert classifier.classify_field("name") == DataClassification.INTERNAL
        assert classifier.classify_field("department") == DataClassification.INTERNAL
        assert classifier.classify_field("project_name") == DataClassification.INTERNAL

    def test_value_based_ssn_detection(self, classifier):
        assert classifier.classify_field("notes", "Call me at 123-45-6789") == (
            DataClassification.RESTRICTED
        )

    def test_value_based_api_key_detection(self, classifier):
        assert classifier.classify_field("config", "sk-" + "abc123456789012345678901") == (
            DataClassification.RESTRICTED
        )

    def test_value_based_github_pat_detection(self, classifier):
        assert classifier.classify_field(
            "token",
            "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789",
        ) == (
            DataClassification.RESTRICTED
        )

    def test_value_based_private_key_detection(self, classifier):
        assert classifier.classify_field("cert", "-----BEGIN " + "PRIVATE KEY-----") == (
            DataClassification.RESTRICTED
        )

    def test_benign_value_not_flagged(self, classifier):
        assert classifier.classify_field("description", "Just a normal description") == (
            DataClassification.INTERNAL
        )

    def test_none_value(self, classifier):
        assert classifier.classify_field("name", None) == DataClassification.INTERNAL

    def test_empty_value(self, classifier):
        assert classifier.classify_field("name", "") == DataClassification.INTERNAL


# ── DataClassifier — filter_for_llm ──────────────────────────────────────────

class TestFilterForLLM:
    def test_filters_restricted_fields(self):
        c = DataClassifier(
            restricted_fields=["ssn"],
            confidential_fields=["email"],
            max_classification="internal",
        )
        props = {"name": "Alice", "ssn": "123-45-6789", "email": "a@b.com", "role": "engineer"}
        result = c.filter_for_llm(props)
        assert "name" in result
        assert "role" in result
        assert "ssn" not in result   # restricted → excluded
        assert "email" not in result  # confidential → excluded (max is internal)

    def test_allows_confidential_when_max_is_confidential(self):
        c = DataClassifier(
            restricted_fields=["ssn"],
            confidential_fields=["email"],
            max_classification="confidential",
        )
        props = {"name": "Alice", "ssn": "secret", "email": "a@b.com"}
        result = c.filter_for_llm(props)
        assert "email" in result      # allowed at confidential level
        assert "ssn" not in result     # still restricted

    def test_allows_everything_when_max_is_restricted(self):
        c = DataClassifier(
            restricted_fields=["ssn"],
            max_classification="restricted",
        )
        props = {"name": "Alice", "ssn": "123-45-6789"}
        result = c.filter_for_llm(props)
        assert "name" in result
        assert "ssn" in result

    def test_public_max_excludes_internal(self):
        c = DataClassifier(max_classification="public")
        props = {"name": "Alice", "department": "Engineering"}
        result = c.filter_for_llm(props)
        # All are INTERNAL by default, so nothing passes at PUBLIC max
        assert len(result) == 0

    def test_empty_properties(self):
        c = DataClassifier(max_classification="internal")
        assert c.filter_for_llm({}) == {}


# ── DataClassifier — redact_for_llm ──────────────────────────────────────────

class TestRedactForLLM:
    def test_redacts_restricted_fields(self):
        c = DataClassifier(
            restricted_fields=["ssn"],
            max_classification="internal",
        )
        props = {"name": "Alice", "ssn": "123-45-6789"}
        result = c.redact_for_llm(props)
        assert result["name"] == "Alice"
        assert result["ssn"] == "[REDACTED:RESTRICTED]"

    def test_redacts_confidential_when_max_is_internal(self):
        c = DataClassifier(
            confidential_fields=["email"],
            max_classification="internal",
        )
        props = {"name": "Alice", "email": "alice@corp.com"}
        result = c.redact_for_llm(props)
        assert result["name"] == "Alice"
        assert result["email"] == "[REDACTED:CONFIDENTIAL]"

    def test_preserves_keys(self):
        """Redaction preserves field names — LLM knows what exists without seeing values."""
        c = DataClassifier(restricted_fields=["password"], max_classification="internal")
        props = {"user": "admin", "password": "s3cr3t"}
        result = c.redact_for_llm(props)
        assert "password" in result
        assert "user" in result

    def test_empty_properties(self):
        c = DataClassifier(max_classification="internal")
        assert c.redact_for_llm({}) == {}


# ── DataClassifier — classify_properties ─────────────────────────────────────

class TestClassifyProperties:
    def test_returns_classification_for_each_field(self):
        c = DataClassifier(
            restricted_fields=["ssn"],
            confidential_fields=["email"],
            max_classification="internal",
        )
        props = {"name": "Alice", "ssn": "123", "email": "a@b.com"}
        result = c.classify_properties(props)
        assert result["name"] == DataClassification.INTERNAL
        assert result["ssn"] == DataClassification.RESTRICTED
        assert result["email"] == DataClassification.CONFIDENTIAL


# ── Singleton factory ────────────────────────────────────────────────────────

class TestSingleton:
    def test_returns_same_instance(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        classifier1 = get_data_classifier()
        classifier2 = get_data_classifier()
        assert classifier1 is classifier2

    def test_reset_creates_new_instance(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        classifier1 = get_data_classifier()
        reset_classifier()
        classifier2 = get_data_classifier()
        assert classifier1 is not classifier2
