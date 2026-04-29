"""Unit tests for the Confluence MCP provider.

Post-A+ cleanup 2026-04-24: the REST fetch path was removed; stdio is
the only live transport. These tests exercise fetch() via a patched
MCP session pool, plus health_check() via its still-REST auth probe.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from aim.mcp.confluence_provider import ConfluenceProvider
from aim.schemas.mcp import ConfluenceContext, MCPContextRequest


def _mock_settings(**overrides):
    defaults = dict(
        confluence_base_url="https://wiki.example.com",
        confluence_email="user@example.com",
        confluence_api_token="secret-token",
        confluence_spaces=["ENG", "OPS"],
        mcp_transport="stdio",
    )
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _make_request(query: str = "auth service", max_results: int = 5) -> MCPContextRequest:
    return MCPContextRequest(query_text=query, max_results_per_provider=max_results)


def _stdio_pool(pages_per_call: list[dict]):
    """Build a patched session pool that returns the given pages list."""
    session = MagicMock()
    session.call_tool = AsyncMock(return_value={
        "content": [{"type": "text", "text": json.dumps(pages_per_call)}],
    })
    pool = MagicMock()
    pool.get_session = AsyncMock(return_value=session)
    return pool


# ── fetch() — stdio path ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_returns_contexts_for_matching_pages():
    pages = [
        {"id": "12345", "title": "Auth Runbook", "space_key": "ENG", "body": "hello"},
        {"id": "67890", "title": "Ops Playbook", "space_key": "OPS", "body": "world"},
    ]
    pool = _stdio_pool(pages)

    with patch("aim.mcp.confluence_provider.get_settings", return_value=_mock_settings()), \
         patch("aim.mcp.client.session.get_session_pool", return_value=pool):
        provider = ConfluenceProvider()
        results = await provider.fetch(_make_request())

    assert len(results) == 2
    for ctx in results:
        assert isinstance(ctx, ConfluenceContext)
        assert len(ctx.pages) == 1


@pytest.mark.asyncio
async def test_fetch_builds_correct_page_fields():
    pages = [{
        "id": "12345",
        "title": "Auth Service Runbook",
        "space_key": "ENG",
        "body": "plain body",
        "url": "https://wiki.example.com/wiki/spaces/ENG/pages/12345",
    }]
    pool = _stdio_pool(pages)

    with patch("aim.mcp.confluence_provider.get_settings", return_value=_mock_settings(confluence_spaces=["ENG"])), \
         patch("aim.mcp.client.session.get_session_pool", return_value=pool):
        provider = ConfluenceProvider()
        results = await provider.fetch(_make_request())

    page = results[0].pages[0]
    assert page.page_id == "12345"
    assert page.title == "Auth Service Runbook"
    assert page.space_key == "ENG"
    assert "12345" in page.url


@pytest.mark.asyncio
async def test_fetch_strips_html_from_body():
    html_body = "<div><p>Hello <b>world</b></p><br/><span>foo  bar</span></div>"
    pages = [{"id": "1", "title": "T", "space_key": "X", "body": html_body}]
    pool = _stdio_pool(pages)

    with patch("aim.mcp.confluence_provider.get_settings", return_value=_mock_settings(confluence_spaces=["X"])), \
         patch("aim.mcp.client.session.get_session_pool", return_value=pool):
        provider = ConfluenceProvider()
        results = await provider.fetch(_make_request())

    body = results[0].pages[0].body_text
    assert "<" not in body
    assert ">" not in body
    assert "Hello" in body
    assert "world" in body
    assert "foo bar" in body


@pytest.mark.asyncio
async def test_fetch_extracts_labels():
    pages = [{
        "id": "2",
        "title": "Labelled Page",
        "space_key": "S",
        "body": "plain",
        "labels": [{"name": "alpha"}, {"name": "beta"}, {"name": "gamma"}],
    }]
    pool = _stdio_pool(pages)

    with patch("aim.mcp.confluence_provider.get_settings", return_value=_mock_settings(confluence_spaces=["S"])), \
         patch("aim.mcp.client.session.get_session_pool", return_value=pool):
        provider = ConfluenceProvider()
        results = await provider.fetch(_make_request())

    assert results[0].pages[0].labels == ["alpha", "beta", "gamma"]


@pytest.mark.asyncio
async def test_fetch_empty_results_returns_empty_list():
    """Upstream returning no content blocks at all yields an empty list."""
    session = MagicMock()
    session.call_tool = AsyncMock(return_value={"content": []})
    pool = MagicMock()
    pool.get_session = AsyncMock(return_value=session)

    with patch("aim.mcp.confluence_provider.get_settings", return_value=_mock_settings()), \
         patch("aim.mcp.client.session.get_session_pool", return_value=pool):
        provider = ConfluenceProvider()
        results = await provider.fetch(_make_request())

    assert results == []


@pytest.mark.asyncio
async def test_fetch_stdio_failure_is_swallowed():
    """A stdio session failure must not propagate; provider returns []."""
    pool = MagicMock()
    pool.get_session = AsyncMock(side_effect=RuntimeError("mcp subprocess died"))

    with patch("aim.mcp.confluence_provider.get_settings", return_value=_mock_settings()), \
         patch("aim.mcp.client.session.get_session_pool", return_value=pool):
        provider = ConfluenceProvider()
        results = await provider.fetch(_make_request())

    assert results == []


@pytest.mark.asyncio
async def test_fetch_skips_when_no_credentials():
    with patch("aim.mcp.confluence_provider.get_settings", return_value=_mock_settings(confluence_api_token="")):
        provider = ConfluenceProvider()
        results = await provider.fetch(_make_request())

    assert results == []


# ── health_check() — still REST (auth probe) ──────────────────────────────────

@pytest.mark.asyncio
async def test_health_check_success():
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("aim.mcp.confluence_provider.get_settings", return_value=_mock_settings()), \
         patch("aim.mcp.confluence_provider.httpx.AsyncClient", return_value=mock_client):
        provider = ConfluenceProvider()
        assert await provider.health_check() is True


@pytest.mark.asyncio
async def test_health_check_non_200():
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 401

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("aim.mcp.confluence_provider.get_settings", return_value=_mock_settings()), \
         patch("aim.mcp.confluence_provider.httpx.AsyncClient", return_value=mock_client):
        provider = ConfluenceProvider()
        assert await provider.health_check() is False


@pytest.mark.asyncio
async def test_health_check_exception():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("unreachable"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("aim.mcp.confluence_provider.get_settings", return_value=_mock_settings()), \
         patch("aim.mcp.confluence_provider.httpx.AsyncClient", return_value=mock_client):
        provider = ConfluenceProvider()
        assert await provider.health_check() is False
