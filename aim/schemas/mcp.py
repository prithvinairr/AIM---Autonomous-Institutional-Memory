"""MCP (Model Context Protocol) context schemas.

Aligned with the MCP specification (https://spec.modelcontextprotocol.io/):
  - Resources: Read-only data sources (Slack messages, Jira issues)
  - Tools: Actions that can be invoked (search, create issue)
  - Capabilities: Declared per-provider via MCPServerCapabilities

JSON-RPC 2.0 transport is available via ``aim.mcp.jsonrpc`` and the
``POST /mcp/jsonrpc`` endpoint (enabled when ``MCP_TRANSPORT=jsonrpc``).
These data models are shared by both native REST and JSON-RPC transports.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class MCPProviderType(StrEnum):
    SLACK = "slack"
    JIRA = "jira"
    CONFLUENCE = "confluence"


# ── MCP Spec-aligned metadata ────────────────────────────────────────────────

class MCPResource(BaseModel):
    """An MCP resource — a readable data source (spec: resources/read)."""
    model_config = ConfigDict(frozen=True)

    uri: str = Field(..., description="Unique resource URI (e.g. slack://channel/general)")
    name: str
    description: str = ""
    mime_type: str = "text/plain"


class MCPTool(BaseModel):
    """An MCP tool — an action the provider can perform (spec: tools/call)."""
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class MCPServerCapabilities(BaseModel):
    """Declares what a provider supports (spec: initialize response)."""
    model_config = ConfigDict(frozen=True)

    provider_type: MCPProviderType
    provider_name: str
    version: str = "1.0.0"
    resources: list[MCPResource] = Field(default_factory=list)
    tools: list[MCPTool] = Field(default_factory=list)
    supports_streaming: bool = False
    transport: str = "native"  # "native", "jsonrpc", or "stdio"


# ── Slack ─────────────────────────────────────────────────────────────────────

class SlackMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    message_id: str
    channel: str
    author: str
    text: str
    timestamp: datetime
    thread_ts: str | None = None
    reactions: list[str] = Field(default_factory=list)
    permalink: str | None = None


class SlackContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    channel: str
    messages: list[SlackMessage]
    query_relevance_score: float = Field(ge=0.0, le=1.0)


# ── Jira ──────────────────────────────────────────────────────────────────────

class JiraIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    issue_key: str           # e.g. "ENG-1234"
    summary: str
    description: str | None = None
    status: str
    assignee: str | None = None
    reporter: str | None = None
    labels: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    url: str
    comments: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class JiraContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    project: str
    issues: list[JiraIssue]
    query_relevance_score: float = Field(ge=0.0, le=1.0)


# ── Confluence ───────────────────────────────────────────────────────────────

class ConfluencePage(BaseModel):
    model_config = ConfigDict(frozen=True)

    page_id: str
    title: str
    space_key: str
    body_text: str = ""
    labels: list[str] = Field(default_factory=list)
    url: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConfluenceContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    space_key: str
    pages: list[ConfluencePage]
    query_relevance_score: float = Field(ge=0.0, le=1.0)


# ── Tool call result ────────────────────────────────────────────────────────

class MCPToolCallResult(BaseModel):
    """Result of an MCP tools/call invocation."""
    model_config = ConfigDict(frozen=True)

    tool_name: str
    provider_type: MCPProviderType
    success: bool = True
    data: list[SlackContext | JiraContext | ConfluenceContext] = Field(default_factory=list)
    error: str | None = None


# ── Unified MCP payload ───────────────────────────────────────────────────────

class MCPContextRequest(BaseModel):
    query_text: str
    providers: list[MCPProviderType] = Field(
        default_factory=lambda: [MCPProviderType.SLACK, MCPProviderType.JIRA]
    )
    slack_channels: list[str] = Field(default_factory=list)
    jira_projects: list[str] = Field(default_factory=list)
    max_results_per_provider: int = Field(default=5, ge=1, le=20)


class MCPContext(BaseModel):
    """Aggregated context pulled from all MCP providers."""

    model_config = ConfigDict(frozen=True)

    context_id: UUID = Field(default_factory=uuid4)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    slack_contexts: list[SlackContext] = Field(default_factory=list)
    jira_contexts: list[JiraContext] = Field(default_factory=list)
    confluence_contexts: list[ConfluenceContext] = Field(default_factory=list)

    @property
    def total_items(self) -> int:
        slack_msgs = sum(len(c.messages) for c in self.slack_contexts)
        jira_issues = sum(len(c.issues) for c in self.jira_contexts)
        confluence_pages = sum(len(c.pages) for c in self.confluence_contexts)
        return slack_msgs + jira_issues + confluence_pages

    def as_text_chunks(self) -> list[tuple[str, str]]:
        """Returns (source_uri, text) pairs for every retrieved item."""
        chunks: list[tuple[str, str]] = []
        for ctx in self.slack_contexts:
            for msg in ctx.messages:
                uri = msg.permalink or f"slack://channel/{ctx.channel}/{msg.message_id}"
                chunks.append((uri, f"[Slack #{ctx.channel}] {msg.author}: {msg.text}"))
        for ctx in self.jira_contexts:
            for issue in ctx.issues:
                text = f"[Jira {issue.issue_key}] {issue.summary}\n{issue.description or ''}"
                chunks.append((issue.url, text))
        for ctx in self.confluence_contexts:
            for page in ctx.pages:
                text = f"[Confluence {page.space_key}/{page.title}] {page.body_text[:500]}"
                chunks.append((page.url, text))
        return chunks
