"""Phase 13 — MCP stdio handshake integration.

Exercises the full JSON-RPC 2.0 protocol sequence the spec requires of any
conforming MCP server: ``initialize`` → ``tools/list`` → ``tools/call``.

The test uses a lightweight fake ``asyncio.subprocess.Process`` rather than
spawning a real MCP server binary (none is guaranteed to be installed in CI).
But the ``send()`` / ``_read_loop()`` paths exercised are the real thing —
this is a genuine protocol round-trip, not a ``send`` method mock.

What this pins:
* The client wraps each method in a valid JSON-RPC 2.0 envelope with unique ids.
* Responses from stdout are correlated back to the right request by id.
* ``error`` responses are raised as ``MCPRemoteError``, not silently discarded.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from aim.mcp.client.stdio_client import MCPRemoteError, StdioMCPClient


# ── Fake asyncio subprocess ─────────────────────────────────────────────────


class _FakeStreamWriter:
    """Asyncio-compatible stdin stand-in. Captures writes and feeds pre-scripted
    responses into the paired reader on each request."""

    def __init__(self, stdout_reader: "_FakeStreamReader", scripted_responses: dict[str, dict]):
        self._stdout = stdout_reader
        self._scripted = scripted_responses
        self.sent: list[dict] = []

    def write(self, data: bytes) -> None:
        # Parse the incoming JSON-RPC request so the fake server can reply.
        for line in data.decode().splitlines():
            if not line.strip():
                continue
            req = json.loads(line)
            self.sent.append(req)
            # Notifications (no id) don't get a response per JSON-RPC spec.
            if "id" not in req:
                continue
            method = req["method"]
            if method not in self._scripted:
                # Default: emit a method-not-found error so unexpected calls
                # surface loudly rather than silently hanging the test.
                response = {
                    "jsonrpc": "2.0",
                    "id": req["id"],
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
            else:
                scripted = self._scripted[method]
                response = {
                    "jsonrpc": "2.0",
                    "id": req["id"],
                    **scripted,
                }
            self._stdout.feed((json.dumps(response) + "\n").encode())

    async def drain(self) -> None:
        return None


class _FakeStreamReader:
    """Asyncio stream reader backed by an in-memory queue."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._closed = False

    def feed(self, data: bytes) -> None:
        self._queue.put_nowait(data)

    def close(self) -> None:
        self._closed = True
        self._queue.put_nowait(b"")

    async def readline(self) -> bytes:
        data = await self._queue.get()
        return data


class _FakeProcess:
    """Minimal duck-typed substitute for ``asyncio.subprocess.Process``."""

    def __init__(self, scripted_responses: dict[str, dict]):
        self.stdout = _FakeStreamReader()
        self.stderr = _FakeStreamReader()
        self.stdin = _FakeStreamWriter(self.stdout, scripted_responses)
        self.pid = 99999
        self.returncode: int | None = None

    def terminate(self) -> None:
        self.returncode = 0
        self.stdout.close()
        self.stderr.close()

    def kill(self) -> None:
        self.terminate()

    async def wait(self) -> int:
        return 0


async def _install_fake(client: StdioMCPClient, scripted: dict[str, dict]) -> _FakeProcess:
    """Plug a fake process into the client without spawning."""
    proc = _FakeProcess(scripted)
    client._process = proc  # type: ignore[assignment]
    client._started = True
    client._reader_task = asyncio.create_task(client._read_loop(), name="fake_reader")
    client._stderr_task = asyncio.create_task(client._stderr_loop(), name="fake_stderr")
    # Let the reader loop start.
    await asyncio.sleep(0)
    return proc


# ── Tests ───────────────────────────────────────────────────────────────────


class TestMCPHandshake:
    async def test_initialize_then_tools_list_then_tools_call(self):
        """The canonical MCP handshake sequence.

        This test does not poke at ``send()``'s internals — it watches the
        JSON on the wire and the shape of the ``result`` returned for each
        step, pinning compatibility with any spec-conforming server."""
        scripted = {
            "initialize": {
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": "fake-mcp-server", "version": "0.0.1"},
                },
            },
            "tools/list": {
                "result": {
                    "tools": [
                        {"name": "slack_search", "description": "search slack",
                         "inputSchema": {"type": "object"}},
                        {"name": "jira_issue_get", "description": "fetch a jira issue",
                         "inputSchema": {"type": "object"}},
                    ],
                },
            },
            "tools/call": {
                "result": {
                    "content": [
                        {"type": "text", "text": "2 messages matched 'outage'"}
                    ],
                    "isError": False,
                },
            },
        }
        client = StdioMCPClient(command="fake", args=[])
        proc = await _install_fake(client, scripted)
        try:
            # Step 1 — initialize
            init_result = await client.send(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "aim-tests", "version": "0.0.1"},
                },
            )
            assert init_result["serverInfo"]["name"] == "fake-mcp-server"
            assert "capabilities" in init_result

            # Step 2 — tools/list
            tools_result = await client.send("tools/list")
            tool_names = {t["name"] for t in tools_result["tools"]}
            assert tool_names == {"slack_search", "jira_issue_get"}

            # Step 3 — tools/call
            call_result = await client.send(
                "tools/call",
                {"name": "slack_search", "arguments": {"query": "outage"}},
            )
            assert call_result["isError"] is False
            assert call_result["content"][0]["text"] == "2 messages matched 'outage'"

            # Protocol invariant: every request got a JSON-RPC 2.0 envelope
            # with a unique monotonically-increasing id.
            sent_ids = [req["id"] for req in proc.stdin.sent]
            assert sent_ids == sorted(sent_ids)
            assert len(set(sent_ids)) == len(sent_ids)
            for req in proc.stdin.sent:
                assert req["jsonrpc"] == "2.0"
        finally:
            # Stop reader task and tear down
            client._started = False
            proc.stdout.close()
            proc.stderr.close()
            # Give the reader one tick to exit cleanly
            await asyncio.sleep(0)
            if client._reader_task:
                client._reader_task.cancel()
            if client._stderr_task:
                client._stderr_task.cancel()

    async def test_error_response_raises_mcp_remote_error(self):
        """A JSON-RPC ``error`` envelope must surface as ``MCPRemoteError`` —
        silent-pass-through on server errors is a protocol bug."""
        scripted = {
            "tools/call": {
                "error": {"code": -32602, "message": "invalid params: 'query' required"},
            },
        }
        client = StdioMCPClient(command="fake", args=[])
        proc = await _install_fake(client, scripted)
        try:
            with pytest.raises(MCPRemoteError) as excinfo:
                await client.send("tools/call", {"name": "slack_search", "arguments": {}})
            assert excinfo.value.code == -32602
            assert "invalid params" in excinfo.value.message
        finally:
            client._started = False
            proc.stdout.close()
            proc.stderr.close()
            await asyncio.sleep(0)
            if client._reader_task:
                client._reader_task.cancel()
            if client._stderr_task:
                client._stderr_task.cancel()

    async def test_unknown_method_receives_method_not_found(self):
        """Belt-and-braces: unscripted methods must fail loudly as
        MCP error -32601, not hang the test."""
        client = StdioMCPClient(command="fake", args=[])
        proc = await _install_fake(client, scripted={})
        try:
            with pytest.raises(MCPRemoteError) as excinfo:
                await client.send("resources/read", {"uri": "nowhere"})
            assert excinfo.value.code == -32601
        finally:
            client._started = False
            proc.stdout.close()
            proc.stderr.close()
            await asyncio.sleep(0)
            if client._reader_task:
                client._reader_task.cancel()
            if client._stderr_task:
                client._stderr_task.cancel()
