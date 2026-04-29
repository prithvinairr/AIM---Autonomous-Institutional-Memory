"""Integration tests for webhook endpoints.

Tests the full HTTP flow: request → signature check → text extract → enqueue.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import time

import pytest
from httpx import AsyncClient

from aim.workers.ingest_worker import IngestWorker, JobKind

# ── Test signing secrets ─────────────────────────────────────────────────────

_SLACK_SECRET = "test-slack-secret-12345"
_JIRA_SECRET = "test-jira-secret-12345"
_CONFLUENCE_SECRET = "test-confluence-secret-12345"


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def _with_secrets(env_vars):
    """Configure webhook signing secrets for integration tests."""
    import os
    os.environ["WEBHOOK_SLACK_SIGNING_SECRET"] = _SLACK_SECRET
    os.environ["WEBHOOK_JIRA_SECRET"] = _JIRA_SECRET
    os.environ["WEBHOOK_CONFLUENCE_SECRET"] = _CONFLUENCE_SECRET


def _sign_slack(body: bytes, secret: str = _SLACK_SECRET) -> tuple[str, str]:
    """Generate valid Slack signature + timestamp for a request body."""
    ts = str(int(time.time()))
    basestring = f"v0:{ts}:{body.decode('utf-8')}"
    sig = "v0=" + _hmac.new(secret.encode(), basestring.encode(), hashlib.sha256).hexdigest()
    return ts, sig


def _sign_hmac(body: bytes, secret: str) -> str:
    """Generate sha256=<hex> signature for Jira/Confluence."""
    return "sha256=" + _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# Slack webhook
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_slack_url_verification(client: AsyncClient, _with_secrets):
    """Slack sends a URL verification challenge on setup — allowed before sig check."""
    body = json.dumps({"type": "url_verification", "challenge": "abc123"}).encode()
    ts, sig = _sign_slack(body)
    resp = await client.post(
        "/webhooks/slack/events",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["challenge"] == "abc123"


@pytest.mark.asyncio
async def test_slack_message_enqueued(client: AsyncClient, _with_secrets):
    """Valid Slack message event should enqueue an extraction job."""
    payload = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "text": "Auth service is experiencing high latency across all regions and causing cascading failures",
            "channel": "C123",
            "ts": "1234567890.123",
        },
    }
    body = json.dumps(payload).encode()
    ts, sig = _sign_slack(body)
    resp = await client.post(
        "/webhooks/slack/events",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "job_id" in data


@pytest.mark.asyncio
async def test_slack_short_text_skipped(client: AsyncClient, _with_secrets):
    """Short messages should be skipped (not worth extracting)."""
    payload = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "text": "ok",
            "channel": "C123",
            "ts": "1234567890.123",
        },
    }
    body = json.dumps(payload).encode()
    ts, sig = _sign_slack(body)
    resp = await client.post(
        "/webhooks/slack/events",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "skipped"


# ═══════════════════════════════════════════════════════════════════════════════
# Jira webhook
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_jira_issue_enqueued(client: AsyncClient, _with_secrets):
    payload = {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "key": "ENG-42",
            "fields": {
                "summary": "Auth service timeout during peak load",
                "description": "Users report 30 second timeouts on the login page during peak hours.",
            },
        },
    }
    body = json.dumps(payload).encode()
    sig = _sign_hmac(body, _JIRA_SECRET)
    resp = await client.post(
        "/webhooks/jira",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "job_id" in data


@pytest.mark.asyncio
async def test_jira_short_text_skipped(client: AsyncClient, _with_secrets):
    payload = {"issue": {"key": "X-1", "fields": {"summary": "hi"}}}
    body = json.dumps(payload).encode()
    sig = _sign_hmac(body, _JIRA_SECRET)
    resp = await client.post(
        "/webhooks/jira",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "skipped"


# ═══════════════════════════════════════════════════════════════════════════════
# Confluence webhook
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_confluence_page_enqueued(client: AsyncClient, _with_secrets):
    payload = {
        "page": {
            "id": "12345",
            "title": "System Architecture Overview",
            "body": {
                "storage": {
                    "value": "<p>This document describes the overall system architecture including microservices and data flow.</p>",
                }
            },
            "_links": {"webui": "https://wiki.example.com/pages/12345"},
        },
    }
    body = json.dumps(payload).encode()
    sig = _sign_hmac(body, _CONFLUENCE_SECRET)
    resp = await client.post(
        "/webhooks/confluence",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "job_id" in data


@pytest.mark.asyncio
async def test_confluence_empty_page_skipped(client: AsyncClient, _with_secrets):
    payload = {"page": {"id": "", "title": "", "body": {}, "_links": {}}}
    body = json.dumps(payload).encode()
    sig = _sign_hmac(body, _CONFLUENCE_SECRET)
    resp = await client.post(
        "/webhooks/confluence",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "skipped"


# ═══════════════════════════════════════════════════════════════════════════════
# Signature enforcement
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_jira_invalid_signature_rejected(client: AsyncClient, _with_secrets):
    """When a secret is configured, invalid signatures should be rejected."""
    payload = {"issue": {"key": "X-1", "fields": {"summary": "Something important happened"}}}
    resp = await client.post(
        "/webhooks/jira",
        json=payload,
        headers={"X-Hub-Signature": "sha256=invalid"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_slack_missing_secret_returns_error(client: AsyncClient, monkeypatch):
    """When webhook secret is NOT configured, endpoint should reject the request."""
    import aim.config
    original = aim.config.get_settings

    class FakeSettings:
        def __getattr__(self, name):
            if name == "webhook_slack_signing_secret":
                return ""
            return getattr(original(), name)

    monkeypatch.setattr("aim.api.routes.webhooks.get_settings", FakeSettings)

    resp = await client.post(
        "/webhooks/slack/events",
        json={"type": "event_callback", "event": {"type": "message", "text": "test text that is long enough to not be skipped right", "channel": "C1", "ts": "1"}},
    )
    # Should be 500 (no secret configured) — verifies P1 #14 fix
    assert resp.status_code == 500
