"""Tests for DataClassifier.classify_text — used by the sovereignty guard."""
from __future__ import annotations

from aim.utils.data_classification import DataClassifier


def test_classify_text_empty():
    c = DataClassifier()
    assert c.classify_text("") == set()


def test_classify_text_clean():
    c = DataClassifier()
    result = c.classify_text("What services depend on Kafka?")
    assert result == {"INTERNAL"}


def test_classify_text_ssn():
    c = DataClassifier()
    result = c.classify_text("The user SSN is 123-45-6789")
    assert "RESTRICTED" in result


def test_classify_text_api_key():
    c = DataClassifier()
    result = c.classify_text("Use key sk_abcdefghijklmnopqrstuvwxyz")
    assert "RESTRICTED" in result


def test_classify_text_github_pat():
    c = DataClassifier()
    result = c.classify_text("Token: ghp_" + "1234567890123456789012345678901234AB")
    assert "RESTRICTED" in result


def test_classify_text_slack_token():
    c = DataClassifier()
    result = c.classify_text("Bot token is xoxb-123456789-abcdefgh")
    assert "RESTRICTED" in result


def test_classify_text_private_key():
    c = DataClassifier()
    result = c.classify_text("-----BEGIN " + "RSA PRIVATE KEY-----\nMIIE...")
    assert "RESTRICTED" in result


def test_classify_text_email_confidential():
    c = DataClassifier()
    result = c.classify_text("Contact email: user@example.com")
    assert "CONFIDENTIAL" in result


def test_classify_text_salary_confidential():
    c = DataClassifier()
    result = c.classify_text("Their salary is $150,000")
    assert "CONFIDENTIAL" in result


def test_classify_text_restricted_takes_precedence():
    """If both restricted and confidential markers found, RESTRICTED wins."""
    c = DataClassifier()
    # SSN is restricted; should short-circuit
    result = c.classify_text("SSN: 123-45-6789 email: user@example.com")
    assert "RESTRICTED" in result
