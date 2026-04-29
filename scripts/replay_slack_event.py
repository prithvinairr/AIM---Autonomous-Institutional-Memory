"""Replay a signed Slack Events API message into AIM.

Useful when a live Slack message was ingested before the extractor understood
the incident phrasing. This exercises the real webhook route, including Slack
signature verification, instead of bypassing the API.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_MESSAGE = (
    "INC-2025-100 just got reported by the SRE team. "
    "Auth service rate limiter started returning 429s after the 10am deploy. "
    "Marcus is on it"
)


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _sign(payload: str, secret: str, timestamp: str) -> str:
    base = f"v0:{timestamp}:{payload}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="http://localhost:8000/webhooks/slack/events",
        help="AIM Slack webhook URL. Use your current trycloudflare URL here.",
    )
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    parser.add_argument("--channel", default="CDEMO")
    parser.add_argument("--team-id", default="TDEMO")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()

    env = _load_env(Path(args.env_file))
    secret = env.get("WEBHOOK_SLACK_SIGNING_SECRET", "")
    if not secret:
        raise SystemExit("WEBHOOK_SLACK_SIGNING_SECRET is missing from .env")

    timestamp = str(int(time.time()))
    event_ts = f"{timestamp}.000100"
    payload = json.dumps(
        {
            "type": "event_callback",
            "team_id": args.team_id,
            "event": {
                "type": "message",
                "channel": args.channel,
                "ts": event_ts,
                "text": args.message,
            },
        },
        separators=(",", ":"),
    )
    request = Request(
        args.url,
        data=payload.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": _sign(payload, secret, timestamp),
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            print(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise SystemExit(f"Request failed: {exc.reason}") from exc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
