"""Webhook endpoints for real-time ingestion from Slack, Jira, and Confluence.

Each endpoint:
  1. Validates the request signature against a shared secret.
  2. Extracts text content from the platform-specific payload.
  3. Enqueues an extraction job on the ingest worker (async — returns 200 immediately).

Signature verification:
  - Slack: HMAC-SHA256 using ``webhook_slack_signing_secret`` and the ``X-Slack-Signature`` header.
  - Jira: HMAC-SHA256 using ``webhook_jira_secret`` and the ``X-Hub-Signature`` header.
  - Confluence: HMAC-SHA256 using ``webhook_confluence_secret`` and the ``X-Hub-Signature`` header.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

import structlog
from fastapi import APIRouter, Header, HTTPException, Request

from aim.config import get_settings
from aim.workers.ingest_worker import get_ingest_worker

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ── Signature verification helpers ───────────────────────────────────────────


def _verify_slack_signature(
    body: bytes,
    timestamp: str,
    signature: str,
    secret: str,
) -> bool:
    """Verify Slack request signature (v0 scheme).

    See: https://api.slack.com/authentication/verifying-requests-from-slack
    """
    if not secret:
        return False

    # Prevent replay attacks — reject requests older than 5 minutes
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False
    if abs(time.time() - ts) > 300:
        return False

    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    computed = "v0=" + hmac.new(
        secret.encode(), basestring.encode(), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed, signature)


def _verify_hmac_sha256(body: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature (Jira / Confluence / generic).

    The ``signature`` header is expected to be ``sha256=<hex>``.
    """
    if not secret:
        return False
    if not signature.startswith("sha256="):
        return False

    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature[7:]  # strip "sha256="
    return hmac.compare_digest(expected, provided)


# ── Text extraction helpers ──────────────────────────────────────────────────


def _extract_slack_text(payload: dict[str, Any]) -> tuple[str, str]:
    """Extract text and source URI from a Slack Events API payload.

    Returns ``(text, source_uri)``.
    """
    event = payload.get("event", {})
    event_type = event.get("type", "")

    if event_type == "message" and "subtype" not in event:
        text = event.get("text", "")
        channel = event.get("channel", "unknown")
        ts = event.get("ts", "")
        return text, f"slack://channel/{channel}/message/{ts}"

    # File shared events
    if event_type == "file_shared":
        file_info = event.get("file", {})
        text = file_info.get("preview", "") or file_info.get("title", "")
        return text, f"slack://file/{file_info.get('id', 'unknown')}"

    return "", ""


def _extract_jira_text(payload: dict[str, Any]) -> tuple[str, str]:
    """Extract text and source URI from a Jira webhook payload.

    Returns ``(text, source_uri)``.
    """
    issue = payload.get("issue", {})
    fields = issue.get("fields", {})
    key = issue.get("key", "")

    parts: list[str] = []
    if summary := fields.get("summary"):
        parts.append(f"Summary: {summary}")
    if desc := fields.get("description"):
        # Jira sends ADF or plain text depending on config
        if isinstance(desc, str):
            parts.append(desc)
        elif isinstance(desc, dict):
            parts.append(_flatten_adf(desc))

    # Include comment if this is a comment event
    comment = payload.get("comment", {})
    if comment_body := comment.get("body"):
        if isinstance(comment_body, str):
            parts.append(comment_body)
        elif isinstance(comment_body, dict):
            parts.append(_flatten_adf(comment_body))

    text = "\n".join(parts)
    base_url = payload.get("issue", {}).get("self", "").split("/rest/")[0]
    uri = f"jira://{key}" if not base_url else f"{base_url}/browse/{key}"

    return text, uri


def _extract_confluence_text(payload: dict[str, Any]) -> tuple[str, str]:
    """Extract text and source URI from a Confluence webhook payload.

    Returns ``(text, source_uri)``.
    """
    page = payload.get("page", {})
    title = page.get("title", "")
    page_id = page.get("id", "")

    # Confluence sends body in storage format or excerpt
    body = page.get("body", {})
    content = ""
    if storage := body.get("storage", {}).get("value", ""):
        # Strip HTML tags for plain text extraction
        import re
        content = re.sub(r"<[^>]+>", " ", storage)
        content = re.sub(r"\s+", " ", content).strip()
    elif excerpt := page.get("excerpt", ""):
        content = excerpt

    text = f"{title}\n{content}" if title else content
    self_link = page.get("_links", {}).get("webui", "")
    uri = f"confluence://page/{page_id}" if not self_link else self_link

    return text, uri


def _flatten_adf(node: dict[str, Any], _depth: int = 0) -> str:
    """Recursively extract plain text from Atlassian Document Format."""
    if _depth > 20:
        return ""
    parts: list[str] = []
    if node.get("type") == "text":
        text = node.get("text", "")
        if isinstance(text, str):
            parts.append(text)
    for child in node.get("content", []):
        if isinstance(child, dict):
            parts.append(_flatten_adf(child, _depth + 1))
    return " ".join(parts)


# ── Slack webhook ────────────────────────────────────────────────────────────


@router.post("/slack/events")
async def slack_events(
    request: Request,
    x_slack_request_timestamp: str = Header("", alias="X-Slack-Request-Timestamp"),
    x_slack_signature: str = Header("", alias="X-Slack-Signature"),
) -> dict[str, Any]:
    """Receive Slack Events API callbacks.

    Handles the initial URL verification challenge and extracts text
    from message events for entity extraction.
    """
    settings = get_settings()
    body = await request.body()
    payload: dict[str, Any] = await request.json()

    # Slack URL verification challenge (sent once during setup)
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    # Verify signature — ALWAYS required when webhook is enabled
    if not settings.webhook_slack_signing_secret:
        log.error("webhook.slack.no_secret_configured")
        raise HTTPException(status_code=500, detail="Webhook signing secret not configured")
    if not _verify_slack_signature(
        body, x_slack_request_timestamp, x_slack_signature,
        settings.webhook_slack_signing_secret,
    ):
        log.warning("webhook.slack.invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    text, source_uri = _extract_slack_text(payload)
    if not text or len(text.strip()) < 20:
        return {"ok": True, "action": "skipped", "reason": "text too short"}

    worker = get_ingest_worker()
    job_id = worker.enqueue_extraction(text, source_uri=source_uri)
    log.info("webhook.slack.enqueued", job_id=job_id, source_uri=source_uri)

    return {"ok": True, "job_id": job_id}


# ── Jira webhook ─────────────────────────────────────────────────────────────


@router.post("/jira")
async def jira_webhook(
    request: Request,
    x_hub_signature: str = Header("", alias="X-Hub-Signature"),
) -> dict[str, Any]:
    """Receive Jira webhook callbacks for issue creation/updates."""
    settings = get_settings()
    body = await request.body()

    if not settings.webhook_jira_secret:
        log.error("webhook.jira.no_secret_configured")
        raise HTTPException(status_code=500, detail="Webhook signing secret not configured")
    if not _verify_hmac_sha256(body, x_hub_signature, settings.webhook_jira_secret):
        log.warning("webhook.jira.invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload: dict[str, Any] = await request.json()
    text, source_uri = _extract_jira_text(payload)
    if not text or len(text.strip()) < 20:
        return {"ok": True, "action": "skipped", "reason": "text too short"}

    worker = get_ingest_worker()
    job_id = worker.enqueue_extraction(text, source_uri=source_uri)
    log.info("webhook.jira.enqueued", job_id=job_id, source_uri=source_uri)

    return {"ok": True, "job_id": job_id}


# ── Confluence webhook ───────────────────────────────────────────────────────


@router.post("/confluence")
async def confluence_webhook(
    request: Request,
    x_hub_signature: str = Header("", alias="X-Hub-Signature"),
) -> dict[str, Any]:
    """Receive Confluence webhook callbacks for page creation/updates."""
    settings = get_settings()
    body = await request.body()

    if not settings.webhook_confluence_secret:
        log.error("webhook.confluence.no_secret_configured")
        raise HTTPException(status_code=500, detail="Webhook signing secret not configured")
    if not _verify_hmac_sha256(
        body, x_hub_signature, settings.webhook_confluence_secret,
    ):
        log.warning("webhook.confluence.invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload: dict[str, Any] = await request.json()
    text, source_uri = _extract_confluence_text(payload)
    if not text or len(text.strip()) < 20:
        return {"ok": True, "action": "skipped", "reason": "text too short"}

    worker = get_ingest_worker()
    job_id = worker.enqueue_extraction(text, source_uri=source_uri)
    log.info("webhook.confluence.enqueued", job_id=job_id, source_uri=source_uri)

    return {"ok": True, "job_id": job_id}
