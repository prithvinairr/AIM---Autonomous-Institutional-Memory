"""Unit tests for webhook endpoints.

Tests cover:
  - Signature verification (Slack v0, HMAC-SHA256)
  - Text extraction from Slack, Jira, and Confluence payloads
  - Minimum text length filtering
  - URL verification challenge handling (Slack)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from aim.api.routes.webhooks import (
    _extract_confluence_text,
    _extract_jira_text,
    _extract_slack_text,
    _flatten_adf,
    _verify_hmac_sha256,
    _verify_slack_signature,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Signature verification
# ═══════════════════════════════════════════════════════════════════════════════


class TestVerifySlackSignature:
    def _make_signature(self, body: str, timestamp: str, secret: str) -> str:
        basestring = f"v0:{timestamp}:{body}"
        return "v0=" + hmac.new(
            secret.encode(), basestring.encode(), hashlib.sha256
        ).hexdigest()

    def test_valid_signature(self):
        body = b'{"type": "event_callback"}'
        ts = str(int(time.time()))
        secret = "test-secret-123"
        sig = self._make_signature(body.decode(), ts, secret)
        assert _verify_slack_signature(body, ts, sig, secret)

    def test_invalid_signature(self):
        body = b'{"type": "event_callback"}'
        ts = str(int(time.time()))
        assert not _verify_slack_signature(body, ts, "v0=invalid", "test-secret")

    def test_replay_attack_rejected(self):
        body = b'{"type": "event_callback"}'
        old_ts = str(int(time.time()) - 600)  # 10 minutes ago
        secret = "test-secret"
        sig = self._make_signature(body.decode(), old_ts, secret)
        assert not _verify_slack_signature(body, old_ts, sig, secret)

    def test_empty_secret(self):
        assert not _verify_slack_signature(b"body", "123", "v0=abc", "")

    def test_invalid_timestamp(self):
        assert not _verify_slack_signature(b"body", "not-a-number", "v0=abc", "secret")


class TestVerifyHmacSha256:
    def test_valid_signature(self):
        body = b'{"issue": {"key": "ENG-123"}}'
        secret = "jira-secret-456"
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_hmac_sha256(body, sig, secret)

    def test_invalid_signature(self):
        assert not _verify_hmac_sha256(b"body", "sha256=wrong", "secret")

    def test_missing_prefix(self):
        assert not _verify_hmac_sha256(b"body", "md5=abc", "secret")

    def test_empty_secret(self):
        assert not _verify_hmac_sha256(b"body", "sha256=abc", "")


# ═══════════════════════════════════════════════════════════════════════════════
# Text extraction
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractSlackText:
    def test_message_event(self):
        payload = {
            "event": {
                "type": "message",
                "text": "Auth service is experiencing high latency",
                "channel": "C123",
                "ts": "1234567890.123",
            }
        }
        text, uri = _extract_slack_text(payload)
        assert "Auth service" in text
        assert "slack://channel/C123/message/1234567890.123" == uri

    def test_message_with_subtype_ignored(self):
        payload = {
            "event": {
                "type": "message",
                "subtype": "bot_message",
                "text": "Bot message",
            }
        }
        text, uri = _extract_slack_text(payload)
        assert text == ""

    def test_file_shared_event(self):
        payload = {
            "event": {
                "type": "file_shared",
                "file": {
                    "id": "F123",
                    "title": "Architecture Diagram",
                    "preview": "This is the system architecture",
                },
            }
        }
        text, uri = _extract_slack_text(payload)
        assert "system architecture" in text
        assert "slack://file/F123" == uri

    def test_unknown_event_type(self):
        payload = {"event": {"type": "app_mention"}}
        text, uri = _extract_slack_text(payload)
        assert text == ""


class TestExtractJiraText:
    def test_issue_with_summary_and_description(self):
        payload = {
            "issue": {
                "key": "ENG-42",
                "fields": {
                    "summary": "Auth service timeout",
                    "description": "Users are experiencing 30s timeouts on login.",
                },
            }
        }
        text, uri = _extract_jira_text(payload)
        assert "Auth service timeout" in text
        assert "30s timeouts" in text
        assert "ENG-42" in uri

    def test_issue_with_adf_description(self):
        payload = {
            "issue": {
                "key": "ENG-99",
                "fields": {
                    "summary": "Bug report",
                    "description": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "Service is down"},
                                ],
                            },
                        ],
                    },
                },
            }
        }
        text, uri = _extract_jira_text(payload)
        assert "Service is down" in text

    def test_comment_event(self):
        payload = {
            "issue": {"key": "ENG-1", "fields": {"summary": "Issue"}},
            "comment": {
                "body": "This was caused by the auth migration"
            },
        }
        text, _ = _extract_jira_text(payload)
        assert "auth migration" in text


class TestExtractConfluenceText:
    def test_page_with_title_and_body(self):
        payload = {
            "page": {
                "id": "12345",
                "title": "System Architecture",
                "body": {
                    "storage": {
                        "value": "<p>This is the <b>architecture</b> overview.</p>",
                    }
                },
                "_links": {"webui": "https://wiki.example.com/pages/12345"},
            }
        }
        text, uri = _extract_confluence_text(payload)
        assert "System Architecture" in text
        assert "architecture" in text
        assert uri == "https://wiki.example.com/pages/12345"

    def test_page_with_excerpt_fallback(self):
        payload = {
            "page": {
                "id": "999",
                "title": "Design Doc",
                "excerpt": "Overview of the microservice design",
                "body": {},
                "_links": {},
            }
        }
        text, uri = _extract_confluence_text(payload)
        assert "microservice design" in text
        assert "confluence://page/999" == uri

    def test_empty_page(self):
        payload = {"page": {"id": "", "title": "", "body": {}, "_links": {}}}
        text, _ = _extract_confluence_text(payload)
        assert text.strip() == ""


class TestFlattenAdf:
    def test_simple_paragraph(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello "},
                        {"type": "text", "text": "World"},
                    ],
                }
            ],
        }
        assert "Hello" in _flatten_adf(adf)
        assert "World" in _flatten_adf(adf)

    def test_deep_nesting_guard(self):
        # Build a deeply nested ADF structure
        node: dict = {"type": "text", "text": "deep"}
        for _ in range(25):
            node = {"type": "paragraph", "content": [node]}
        # Should not crash; depth guard limits recursion
        result = _flatten_adf(node)
        assert isinstance(result, str)
