"""Jira MCP Provider.

Uses the reference MCP spec transport: spawns an upstream MCP server
subprocess (e.g. ``mcp-atlassian``) and delegates via JSON-RPC 2.0 over
stdio.

Config guarantees stdio is the only live transport (``mcp_transport``
validator at ``aim/config.py`` rejects ``native``; ``jsonrpc`` raises
NotImplementedError in __init__). Post-A+ cleanup 2026-04-24 removed
the dead Jira REST + JQL fallback that preceded MCP adherence.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from aim.config import get_settings
from aim.schemas.mcp import (
    JiraContext,
    JiraIssue,
    MCPContextRequest,
    MCPProviderType,
    MCPResource,
    MCPServerCapabilities,
    MCPTool,
)

log = structlog.get_logger(__name__)


class JiraProvider:
    provider_type = MCPProviderType.JIRA

    def __init__(self) -> None:
        self._settings = get_settings()
        token = base64.b64encode(
            f"{self._settings.jira_email}:{self._settings.jira_api_token}".encode()
        ).decode()
        self._headers = {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._base = self._settings.jira_base_url.rstrip("/")
        self._transport = self._settings.mcp_transport
        if self._transport == "jsonrpc":
            raise NotImplementedError(
                "JiraProvider: mcp_transport='jsonrpc' is reserved for a future "
                "HTTP client transport and is not yet implemented. Use 'stdio' "
                "for real MCP protocol adherence, or leave the default for REST."
            )

    def get_capabilities(self) -> MCPServerCapabilities:
        projects = self._settings.jira_default_projects
        return MCPServerCapabilities(
            provider_type=MCPProviderType.JIRA,
            provider_name="JiraProvider",
            resources=[
                MCPResource(
                    uri=f"jira://project/{proj}",
                    name=proj,
                    description=f"Jira project {proj} issues and tickets",
                    mime_type="application/json",
                )
                for proj in projects
            ],
            tools=[
                MCPTool(
                    name="jira_search",
                    description="Search Jira issues by text query across projects",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "projects": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["query"],
                    },
                ),
            ],
        )

    async def fetch(self, request: MCPContextRequest) -> list[JiraContext]:
        if not self._settings.jira_api_token:
            return []

        projects = request.jira_projects or self._settings.jira_default_projects
        if not projects:
            return []

        # Only stdio reaches here — __init__ rejects jsonrpc, validator
        # rejects native.
        return await self._fetch_via_stdio(request, projects)

    async def _fetch_via_stdio(
        self, request: MCPContextRequest, projects: list[str],
    ) -> list[JiraContext]:
        """Fetch Jira issues via MCP stdio subprocess.

        Parses the MCP tool response into real JiraIssue objects, preserving
        the real issue key (PROJ-123), status, assignee, and URL. The
        ``mcp-atlassian`` server returns structured JSON in content text blocks.
        """
        import json as _json
        from aim.schemas.mcp import MCPProviderType as _PT

        try:
            from aim.mcp.client.session import get_session_pool
            pool = get_session_pool()
            session = await pool.get_session(_PT.JIRA)

            result = await session.call_tool("jira_search", {
                "query": request.query_text,
                "projects": projects,
            })

            by_project: dict[str, list[JiraIssue]] = {}
            default_project = projects[0] if projects else "unknown"
            content_items = result.get("content") or []

            for item in content_items:
                if not isinstance(item, dict) or item.get("type") != "text":
                    continue
                text = item.get("text", "")
                if not text:
                    continue
                parsed = _try_parse_issues(text)
                if parsed:
                    for raw in parsed:
                        key = raw.get("key") or raw.get("issue_key")
                        project = default_project
                        if isinstance(key, str) and "-" in key:
                            project = key.split("-", 1)[0]
                        fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else raw
                        status = fields.get("status")
                        if isinstance(status, dict):
                            status = status.get("name", "")
                        assignee = fields.get("assignee")
                        if isinstance(assignee, dict):
                            assignee = assignee.get("displayName")
                        reporter = fields.get("reporter")
                        if isinstance(reporter, dict):
                            reporter = reporter.get("displayName")
                        created = _parse_jira_dt(fields.get("created", ""))
                        updated = _parse_jira_dt(fields.get("updated", ""))
                        url = raw.get("url") or raw.get("permalink") or (
                            f"{self._base}/browse/{key}" if key and self._base else ""
                        )
                        by_project.setdefault(project, []).append(
                            JiraIssue(
                                issue_key=str(key) if key else f"MCP-{len(by_project.get(project, []))}",
                                summary=str(fields.get("summary", ""))[:500],
                                description=_coerce_description(fields.get("description")),
                                status=str(status) if status else "",
                                assignee=str(assignee) if assignee else None,
                                reporter=str(reporter) if reporter else None,
                                labels=fields.get("labels") or [],
                                created_at=created,
                                updated_at=updated,
                                url=url,
                                comments=_coerce_comments(fields.get("comments") or fields.get("comment")),
                            )
                        )
                else:
                    # Plain prose: preserve as a single issue with a namespaced key
                    by_project.setdefault(default_project, []).append(
                        JiraIssue(
                            issue_key=f"{default_project}-MCP-{len(by_project.get(default_project, []))}",
                            summary=text[:200],
                            description=text,
                            status="",
                            url="",
                        )
                    )

            contexts: list[JiraContext] = [
                JiraContext(
                    project=project,
                    issues=issues,
                    query_relevance_score=0.85,
                )
                for project, issues in by_project.items()
                if issues
            ]

            log.debug(
                "jira.stdio_fetched",
                contexts=len(contexts),
                total_issues=sum(len(c.issues) for c in contexts),
            )
            return contexts

        except Exception as exc:
            log.warning("jira.stdio_fallback", error=str(exc))
            return []

    async def health_check(self) -> bool:
        if not self._settings.jira_api_token:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self._base}/rest/api/3/myself", headers=self._headers
                )
                return resp.status_code == 200
        except Exception as exc:
            log.error("jira.health_check_failed", error=str(exc))
            return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _try_parse_issues(text: str) -> list[dict] | None:
    """Parse an MCP text block as a JSON list of Jira issues."""
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
        issues = obj.get("issues") or obj.get("results") or obj.get("data")
        if isinstance(issues, list):
            return [x for x in issues if isinstance(x, dict)]
    return None


def _coerce_description(value: Any) -> str | None:
    """Accept Atlassian Document Format, plain string, or None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value[:4000] or None
    if isinstance(value, dict):
        return _extract_adf_text(value)
    return None


def _coerce_comments(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for c in value:
            if isinstance(c, str):
                out.append(c)
            elif isinstance(c, dict):
                text = _extract_adf_text(c.get("body")) or c.get("body")
                if isinstance(text, str):
                    out.append(text)
        return out
    if isinstance(value, dict):
        return _extract_comments(value)
    return []


def _parse_jira_dt(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        log.warning("jira.datetime_parse_failed", value=value)
        return datetime.now(timezone.utc)


def _extract_adf_text(adf: Any, _depth: int = 0) -> str | None:
    """Recursively extract plain text from Atlassian Document Format."""
    if not isinstance(adf, dict) or _depth > 20:  # guard against pathological nesting
        return None
    parts: list[str] = []

    def _walk(node: Any, depth: int) -> None:
        if not isinstance(node, dict) or depth > 20:
            return
        if node.get("type") == "text":
            text = node.get("text")
            if isinstance(text, str):
                parts.append(text)
        for child in node.get("content") or []:
            _walk(child, depth + 1)

    _walk(adf, 0)
    return " ".join(parts) or None


def _extract_comments(comment_field: dict[str, Any]) -> list[str]:
    comments: list[str] = []
    for c in comment_field.get("comments") or []:
        if not isinstance(c, dict):
            continue
        text = _extract_adf_text(c.get("body"))
        if text:
            comments.append(text)
    return comments
