"""Phase 13 — real subprocess integration test for ``StdioMCPClient``.

The unit-level handshake test (``test_phase13_mcp_handshake.py``) uses a
fake ``asyncio.subprocess.Process`` and drives the protocol in-memory. It
pins the JSON-RPC envelope shape and the id-correlation logic, but it
bypasses the actual OS subprocess boundary — the PIPE wiring, flush
semantics, and line-based framing.

This test closes that gap: it spawns ``tests/fixtures/fake_mcp_server.py``
as a real ``python`` subprocess and drives the canonical MCP handshake
through the real stdin/stdout streams. If the fixture process isn't
reachable (e.g. ``python`` not on PATH in CI), the test is skipped rather
than failing — the unit-level test still covers the protocol semantics.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from aim.mcp.client.stdio_client import MCPRemoteError, StdioMCPClient


_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "fake_mcp_server.py"


def _python_cmd() -> str | None:
    """Return the python command used to spawn the fixture, or None if
    we can't find one. Prefers ``sys.executable`` so the subprocess uses
    the same interpreter as the test — avoids 'python' being a different
    Windows Store shim."""
    if sys.executable:
        return sys.executable
    for candidate in ("python3", "python"):
        if shutil.which(candidate):
            return candidate
    return None


@pytest.fixture
async def live_client():
    """Spawn the fixture server and yield a connected client.

    Guaranteed to stop the subprocess on teardown even if the test
    crashes mid-call, so we don't leak file descriptors in CI."""
    py = _python_cmd()
    if py is None or not _FIXTURE.exists():
        pytest.skip("python interpreter or fixture server unavailable")

    client = StdioMCPClient(command=py, args=[str(_FIXTURE)])
    await client.start()
    try:
        yield client
    finally:
        await client.stop()


class TestRealSubprocessHandshake:
    async def test_initialize_returns_server_info(self, live_client):
        """initialize is the first MCP method any conforming server answers.
        Covers: fixture spawned, stdin received our JSON, stdout piped back,
        client's reader correlated the id."""
        result = await live_client.send(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "aim-tests", "version": "0.0.1"},
            },
        )
        assert result["serverInfo"]["name"] == "aim-fake-mcp"
        assert "capabilities" in result

    async def test_tools_list_returns_declared_tools(self, live_client):
        result = await live_client.send("tools/list")
        names = {t["name"] for t in result["tools"]}
        assert names == {"echo", "add"}

    async def test_tools_call_echo_round_trips_arguments(self, live_client):
        """Writes arguments to the subprocess, reads the echo response back.
        If the subprocess boundary had any framing bug (missing newline,
        stdout not flushed, stdin buffered) this test would hang and fail
        via the client's internal timeout rather than silently pass."""
        import json as _json

        result = await live_client.send(
            "tools/call",
            {"name": "echo", "arguments": {"x": 1, "y": "two"}},
        )
        assert result["isError"] is False
        assert _json.loads(result["content"][0]["text"]) == {"x": 1, "y": "two"}

    async def test_tools_call_add_executes_server_side_logic(self, live_client):
        """Verifies the server-side handler ran (not just a scripted echo).
        The fixture actually parses the ints and sums them — if the
        argument dict didn't round-trip, this assertion fails."""
        result = await live_client.send(
            "tools/call",
            {"name": "add", "arguments": {"a": 40, "b": 2}},
        )
        assert result["content"][0]["text"] == "42"

    async def test_unknown_method_raises_mcp_remote_error(self, live_client):
        """An error envelope from the real subprocess must raise, not
        silently return None. This is the contract for any spec-conforming
        MCP server and mirrors the unit test's expectation."""
        with pytest.raises(MCPRemoteError) as excinfo:
            await live_client.send("resources/read", {"uri": "nowhere"})
        assert excinfo.value.code == -32601
