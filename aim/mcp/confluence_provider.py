"""Confluence MCP Provider.

Uses the reference MCP spec transport: spawns an upstream MCP server
subprocess (e.g. ``mcp-atlassian``) and delegates via JSON-RPC 2.0 over
stdio.

Config guarantees stdio is the only live transport (``mcp_transport``
validator at ``aim/config.py`` rejects ``native``; ``jsonrpc`` raises
NotImplementedError in __init__). Post-A+ cleanup 2026-04-24 removed
the dead Confluence REST + CQL fallback that preceded MCP adherence.

Activate by setting ``CONFLUENCE_API_TOKEN`` and ``CONFLUENCE_BASE_URL``
in environment variables.
"""
from __future__ import annotations

import httpx
import structlog

from aim.config import get_settings
from aim.schemas.mcp import (
    ConfluenceContext,
    ConfluencePage,
    MCPContextRequest,
    MCPProviderType,
    MCPResource,
    MCPServerCapabilities,
    MCPTool,
)

log = structlog.get_logger(__name__)


def _try_parse_pages(text: str) -> list[dict] | None:
    """Parse an MCP text block as a JSON list of Confluence pages."""
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
        pages = obj.get("pages") or obj.get("results") or obj.get("data")
        if isinstance(pages, list):
            return [x for x in pages if isinstance(x, dict)]
    return None


class ConfluenceProvider:
    """MCP provider for Atlassian Confluence."""

    provider_type = MCPProviderType.CONFLUENCE

    def __init__(self) -> None:
        self._settings = get_settings()
        self._base_url = getattr(self._settings, "confluence_base_url", "").rstrip("/")
        self._email = getattr(self._settings, "confluence_email", "")
        self._token = getattr(self._settings, "confluence_api_token", "")
        self._transport = self._settings.mcp_transport
        if self._transport == "jsonrpc":
            raise NotImplementedError(
                "ConfluenceProvider: mcp_transport='jsonrpc' is reserved for "
                "a future HTTP client transport and is not yet implemented. "
                "Use 'stdio' for real MCP protocol adherence."
            )

    def get_capabilities(self) -> MCPServerCapabilities:
        spaces = getattr(self._settings, "confluence_spaces", ["ENG"])
        return MCPServerCapabilities(
            provider_type=self.provider_type,
            provider_name="ConfluenceProvider",
            version="1.0.0",
            resources=[
                MCPResource(
                    uri=f"confluence://space/{space}",
                    name=f"Confluence Space: {space}",
                    description=f"Pages in the {space} Confluence space",
                    mime_type="text/html",
                )
                for space in spaces
            ],
            tools=[
                MCPTool(
                    name="confluence_search",
                    description="Search Confluence pages using CQL",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "spaces": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Confluence space keys to search",
                            },
                        },
                        "required": ["query"],
                    },
                ),
            ],
        )

    async def fetch(self, request: MCPContextRequest) -> list[ConfluenceContext]:
        if not self._token or not self._base_url:
            return []

        spaces = getattr(self._settings, "confluence_spaces", ["ENG"])

        # Only stdio reaches here — __init__ rejects jsonrpc, validator
        # rejects native.
        return await self._fetch_via_stdio(request, spaces)

    async def _fetch_via_stdio(
        self, request: MCPContextRequest, spaces: list[str],
    ) -> list[ConfluenceContext]:
        """Fetch Confluence pages via MCP stdio subprocess."""
        import json as _json

        try:
            from aim.mcp.client.session import get_session_pool
            pool = get_session_pool()
            session = await pool.get_session(MCPProviderType.CONFLUENCE)

            result = await session.call_tool("confluence_search", {
                "query": request.query_text,
                "spaces": spaces,
            })

            by_space: dict[str, list[ConfluencePage]] = {}
            default_space = spaces[0] if spaces else "unknown"
            content_items = result.get("content") or []

            for item in content_items:
                if not isinstance(item, dict) or item.get("type") != "text":
                    continue
                text = item.get("text", "")
                if not text:
                    continue
                parsed = _try_parse_pages(text)
                if parsed:
                    for raw in parsed:
                        page_id = str(raw.get("id") or raw.get("page_id") or "")
                        space_key = str(raw.get("space_key") or raw.get("space") or default_space)
                        title = str(raw.get("title") or "")
                        body = raw.get("body") or raw.get("content") or raw.get("text") or ""
                        if isinstance(body, dict):
                            body = body.get("storage", {}).get("value", "") or body.get("text", "")
                        # Strip HTML if present
                        import re as _re
                        plain = _re.sub(r"<[^>]+>", " ", str(body))
                        plain = _re.sub(r"\s+", " ", plain).strip()
                        labels_raw = raw.get("labels") or []
                        labels = [
                            (l.get("name") if isinstance(l, dict) else str(l))
                            for l in labels_raw
                        ]
                        url = raw.get("url") or raw.get("link") or (
                            f"{self._base_url}/wiki{raw.get('_links', {}).get('webui', '')}"
                            if self._base_url else ""
                        )
                        by_space.setdefault(space_key, []).append(
                            ConfluencePage(
                                page_id=page_id or f"mcp-{len(by_space.get(space_key, []))}",
                                title=title,
                                space_key=space_key,
                                body_text=plain[:2000],
                                labels=[l for l in labels if l],
                                url=url,
                            )
                        )
                else:
                    by_space.setdefault(default_space, []).append(
                        ConfluencePage(
                            page_id=f"mcp-{default_space}-{len(by_space.get(default_space, []))}",
                            title=text[:120],
                            space_key=default_space,
                            body_text=text[:2000],
                            labels=[],
                            url="",
                        )
                    )

            contexts = [
                ConfluenceContext(
                    space_key=space,
                    pages=pages,
                    query_relevance_score=0.85,
                )
                for space, pages in by_space.items()
                if pages
            ]
            log.debug(
                "confluence.stdio_fetched",
                contexts=len(contexts),
                total_pages=sum(len(c.pages) for c in contexts),
            )
            return contexts

        except Exception as exc:
            log.warning("confluence.stdio_fallback", error=str(exc))
            return []

    async def health_check(self) -> bool:
        if not self._token or not self._base_url:
            return False
        try:
            import base64
            auth_header = base64.b64encode(
                f"{self._email}:{self._token}".encode()
            ).decode()
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self._base_url}/rest/api/user/current",
                    headers={"Authorization": f"Basic {auth_header}"},
                )
                return resp.status_code == 200
        except Exception:
            return False
