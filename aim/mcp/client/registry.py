"""MCP server subprocess registry.

Maps provider types to the command + args needed to spawn their upstream
MCP server.  Environment variables (API tokens) are passed through at
spawn time — never stored in the registry itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aim.schemas.mcp import MCPProviderType


@dataclass(frozen=True)
class MCPServerSpec:
    """Specification for spawning an upstream MCP server subprocess."""

    command: str
    args: list[str] = field(default_factory=list)
    env_keys: list[str] = field(default_factory=list)
    """Environment variable names that must be passed through to the subprocess."""

    def build_env(self, settings: Any) -> dict[str, str]:
        """Extract required env vars from settings (or os.environ fallback)."""
        import os
        env: dict[str, str] = {}
        for key in self.env_keys:
            # Try settings attribute (lowercase, no prefix)
            attr = key.lower()
            val = getattr(settings, attr, None)
            if val:
                env[key] = str(val)
            elif key in os.environ:
                env[key] = os.environ[key]
        return env


# Default upstream MCP servers for each provider type.
# These use the official Model Context Protocol community servers.
_DEFAULT_REGISTRY: dict[MCPProviderType, MCPServerSpec] = {
    MCPProviderType.SLACK: MCPServerSpec(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-slack"],
        env_keys=["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"],
    ),
    MCPProviderType.JIRA: MCPServerSpec(
        command="uvx",
        args=["mcp-atlassian", "--jira-url", "{jira_base_url}"],
        env_keys=["JIRA_EMAIL", "JIRA_API_TOKEN"],
    ),
    MCPProviderType.CONFLUENCE: MCPServerSpec(
        command="uvx",
        args=["mcp-atlassian", "--confluence-url", "{confluence_base_url}"],
        env_keys=["CONFLUENCE_EMAIL", "CONFLUENCE_API_TOKEN"],
    ),
}


def get_server_spec(provider_type: MCPProviderType) -> MCPServerSpec | None:
    """Look up the MCPServerSpec for a provider type."""
    return _DEFAULT_REGISTRY.get(provider_type)


def register_server(provider_type: MCPProviderType, spec: MCPServerSpec) -> None:
    """Register a custom MCP server spec (for extensions/testing)."""
    _DEFAULT_REGISTRY[provider_type] = spec


def list_registered() -> dict[MCPProviderType, MCPServerSpec]:
    """Return a copy of the current registry."""
    return dict(_DEFAULT_REGISTRY)
