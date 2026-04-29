"""Slack MCP Provider.

Uses the reference MCP spec transport: spawns an upstream MCP server
subprocess (e.g. ``@modelcontextprotocol/server-slack``) and delegates
via JSON-RPC 2.0 over stdio.

Config guarantees stdio is the only live transport (``mcp_transport``
validator at ``aim/config.py`` rejects ``native``; ``jsonrpc`` raises
NotImplementedError in __init__). Post-A+ cleanup 2026-04-24 removed
the dead Slack Web API REST fallback that preceded MCP adherence.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import structlog

from aim.config import get_settings
from aim.schemas.mcp import (
    MCPContextRequest,
    MCPProviderType,
    MCPResource,
    MCPServerCapabilities,
    MCPTool,
    SlackContext,
    SlackMessage,
)

log = structlog.get_logger(__name__)

_SLACK_API_BASE = "https://slack.com/api"


def _try_parse_messages(text: str) -> list[dict] | None:
    """Attempt to parse an MCP text block as a JSON list-of-messages.

    Returns the list if successful, None if the text is plain prose.
    Accepts both a bare list and an object with a "messages" key.
    """
    import json as _json
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        obj = _json.loads(stripped)
    except _json.JSONDecodeError:
        return None
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        msgs = obj.get("messages") or obj.get("matches") or obj.get("results")
        if isinstance(msgs, list):
            return [x for x in msgs if isinstance(x, dict)]
    return None


class SlackProvider:
    provider_type = MCPProviderType.SLACK

    def __init__(self) -> None:
        self._settings = get_settings()
        self._headers = {
            "Authorization": f"Bearer {self._settings.slack_bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        self._transport = self._settings.mcp_transport
        if self._transport == "jsonrpc":
            raise NotImplementedError(
                "SlackProvider: mcp_transport='jsonrpc' is reserved for a future "
                "HTTP client transport and is not yet implemented. Use 'stdio' "
                "for real MCP protocol adherence, or leave the default for REST."
            )

    def get_capabilities(self) -> MCPServerCapabilities:
        channels = self._settings.slack_default_channels
        return MCPServerCapabilities(
            provider_type=MCPProviderType.SLACK,
            provider_name="SlackProvider",
            resources=[
                MCPResource(
                    uri=f"slack://channel/{ch}",
                    name=f"#{ch}",
                    description=f"Slack channel #{ch} messages",
                    mime_type="text/plain",
                )
                for ch in channels
            ],
            tools=[
                MCPTool(
                    name="slack_search",
                    description="Search Slack messages by keyword across channels",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "channels": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["query"],
                    },
                ),
            ],
        )

    async def fetch(self, request: MCPContextRequest) -> list[SlackContext]:
        if not self._settings.slack_bot_token:
            return []

        channels = request.slack_channels or self._settings.slack_default_channels
        if not channels:
            return []

        # Only stdio reaches here — __init__ rejects jsonrpc, validator
        # rejects native.
        return await self._fetch_via_stdio(request, channels)

    async def _fetch_via_stdio(
        self, request: MCPContextRequest, channels: list[str],
    ) -> list[SlackContext]:
        """Fetch Slack messages via MCP stdio subprocess.

        Parses the MCP tool response into real SlackMessage objects.
        The ``@modelcontextprotocol/server-slack`` server returns content
        blocks where ``text`` is a JSON-encoded list of messages. We also
        accept raw text for servers that return plain prose.
        """
        import json as _json

        try:
            from aim.mcp.client.session import get_session_pool
            pool = get_session_pool()
            session = await pool.get_session(MCPProviderType.SLACK)

            result = await session.call_tool("slack_search", {
                "query": request.query_text,
                "channels": channels,
            })

            contexts: list[SlackContext] = []
            default_channel = channels[0] if channels else "unknown"
            content_items = result.get("content") or []

            # Group parsed messages by channel
            by_channel: dict[str, list[SlackMessage]] = {}

            for item in content_items:
                if not isinstance(item, dict):
                    continue
                itype = item.get("type")
                if itype == "text":
                    text = item.get("text", "")
                    if not text:
                        continue
                    parsed = _try_parse_messages(text)
                    if parsed:
                        # Structured JSON payload — preserve native fields.
                        for m in parsed:
                            channel = m.get("channel") or m.get("channel_id") or default_channel
                            ts_raw = m.get("ts") or m.get("timestamp")
                            try:
                                if isinstance(ts_raw, (int, float)):
                                    ts = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
                                elif isinstance(ts_raw, str) and ts_raw:
                                    ts = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
                                else:
                                    ts = datetime.now(timezone.utc)
                            except (ValueError, TypeError):
                                ts = datetime.now(timezone.utc)
                            msg_id = m.get("id") or m.get("message_id")
                            if not msg_id and ts_raw is not None:
                                msg_id = f"{channel}_{ts_raw}"
                            if not msg_id:
                                msg_id = f"stdio_{channel}_{len(by_channel.get(channel, []))}"
                            by_channel.setdefault(channel, []).append(
                                SlackMessage(
                                    message_id=str(msg_id),
                                    channel=str(channel),
                                    author=str(m.get("user") or m.get("author") or m.get("username") or "unknown"),
                                    text=str(m.get("text", ""))[:2000],
                                    timestamp=ts,
                                    thread_ts=m.get("thread_ts"),
                                    permalink=m.get("permalink"),
                                )
                            )
                    else:
                        # Plain prose result — preserve it without fabricating IDs.
                        by_channel.setdefault(default_channel, []).append(
                            SlackMessage(
                                message_id=f"{default_channel}_mcp_{len(by_channel.get(default_channel, []))}",
                                channel=default_channel,
                                author="mcp:slack",
                                text=text[:2000],
                                timestamp=datetime.now(timezone.utc),
                            )
                        )
                elif itype == "resource":
                    # MCP resource reference — follow via resources/read if desired.
                    continue

            for channel, msgs in by_channel.items():
                if msgs:
                    contexts.append(SlackContext(
                        channel=channel,
                        messages=msgs,
                        query_relevance_score=0.85,
                    ))

            log.debug("slack.stdio_fetched", contexts=len(contexts), total_messages=sum(len(c.messages) for c in contexts))
            return contexts

        except Exception as exc:
            log.warning("slack.stdio_fallback", error=str(exc))
            return []

    async def health_check(self) -> bool:
        if not self._settings.slack_bot_token:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{_SLACK_API_BASE}/auth.test",
                    headers=self._headers,
                )
                return resp.json().get("ok", False)
        except Exception as exc:
            log.error("slack.health_check_failed", error=str(exc))
            return False
