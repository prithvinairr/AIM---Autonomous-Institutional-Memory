"""Low-level MCP stdio transport.

Spawns an MCP server subprocess and communicates via line-delimited JSON-RPC
2.0 over stdin/stdout.  Each request gets a unique ``id`` for correlation.

Usage::

    client = StdioMCPClient(command="npx", args=["-y", "@modelcontextprotocol/server-slack"])
    await client.start(env={"SLACK_BOT_TOKEN": "xoxb-..."})
    result = await client.send("tools/call", {"name": "slack_search", "arguments": {"query": "outage"}})
    await client.stop()
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = 30.0


class StdioMCPClient:
    """Async subprocess wrapper for MCP stdio transport."""

    def __init__(self, command: str, args: list[str] | None = None) -> None:
        self._command = command
        self._args = args or []
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future[dict]] = {}
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._started = False
        # Notification dispatch table: method → callback(params_dict)
        self._notification_handlers: dict[str, Any] = {}
        # Respawn configuration
        self._env: dict[str, str] | None = None
        self._max_respawns = 3
        self._respawn_count = 0

    def on_notification(self, method: str, handler) -> None:
        """Register a handler for server-initiated notifications."""
        self._notification_handlers[method] = handler

    @property
    def alive(self) -> bool:
        return self._started and self._process is not None and self._process.returncode is None

    async def start(self, env: dict[str, str] | None = None) -> None:
        """Spawn the MCP server subprocess."""
        if self._started:
            return

        # Stash env for potential respawn
        if env is not None:
            self._env = env
        full_env = {**os.environ, **(env or {})}

        self._process = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
        )
        self._started = True
        self._reader_task = asyncio.create_task(self._read_loop(), name="mcp_stdio_reader")
        self._stderr_task = asyncio.create_task(self._stderr_loop(), name="mcp_stdio_stderr")
        log.info(
            "mcp_stdio.started",
            command=self._command,
            args=self._args,
            pid=self._process.pid,
        )

    async def stop(self) -> None:
        """Gracefully terminate the subprocess."""
        if not self._started or self._process is None:
            return

        self._started = False

        # Cancel pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

        # Cancel reader
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass

        # Cancel stderr drain
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except (asyncio.CancelledError, Exception):
                pass

        # Terminate process
        try:
            self._process.terminate()
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                self._process.kill()
            except ProcessLookupError:
                pass

        log.info("mcp_stdio.stopped", command=self._command)

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 request and await the response."""
        if not self.alive:
            raise RuntimeError("MCP stdio client is not running")

        assert self._process is not None
        assert self._process.stdin is not None

        self._request_id += 1
        req_id = self._request_id

        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        future: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        line = json.dumps(request) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise
        except asyncio.CancelledError:
            self._pending.pop(req_id, None)
            raise

    async def notify(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Send a JSON-RPC 2.0 notification (no response expected).

        Used for client → server messages that don't expect a reply, such as
        ``notifications/initialized`` after the handshake completes.
        """
        if not self.alive:
            raise RuntimeError("MCP stdio client is not running")

        assert self._process is not None
        assert self._process.stdin is not None

        request = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            request["params"] = params

        line = json.dumps(request) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

    async def _stderr_loop(self) -> None:
        """Drain the subprocess stderr and log at WARNING so server startup
        errors and diagnostics are surfaced rather than silently dropped."""
        assert self._process is not None
        assert self._process.stderr is not None

        try:
            while self._started:
                line = await self._process.stderr.readline()
                if not line:
                    break
                text = line.decode(errors="replace").rstrip()
                if text:
                    log.warning("mcp_stdio.stderr", command=self._command, line=text[:500])
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.debug("mcp_stdio.stderr_reader_error", error=str(exc))

    async def _read_loop(self) -> None:
        """Read line-delimited JSON-RPC responses from stdout."""
        assert self._process is not None
        assert self._process.stdout is not None

        try:
            while self._started:
                line = await self._process.stdout.readline()
                if not line:
                    break

                try:
                    msg = json.loads(line.decode().strip())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                req_id = msg.get("id")
                if req_id is not None and req_id in self._pending:
                    future = self._pending.pop(req_id)
                    if not future.done():
                        if "error" in msg:
                            future.set_exception(
                                MCPRemoteError(
                                    msg["error"].get("code", -1),
                                    msg["error"].get("message", "Unknown error"),
                                )
                            )
                        else:
                            future.set_result(msg.get("result", {}))
                # Notifications (no id) — dispatch to registered handlers.
                elif req_id is None and "method" in msg:
                    method = msg["method"]
                    log.debug("mcp_stdio.notification", method=method)
                    # Dispatch to registered notification handlers
                    handler = self._notification_handlers.get(method)
                    if handler is not None:
                        try:
                            handler(msg.get("params", {}))
                        except Exception as exc:
                            log.debug("mcp_stdio.notification_handler_error",
                                      method=method, error=str(exc))

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.error("mcp_stdio.reader_error", error=str(exc))
        finally:
            # Fail all remaining pending futures
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("MCP stdio reader stopped"))
            self._pending.clear()


class MCPRemoteError(Exception):
    """Error returned by the upstream MCP server."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"MCP error {code}: {message}")
