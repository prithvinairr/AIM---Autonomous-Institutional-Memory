"""Minimal stdio MCP server — fixture for subprocess integration tests.

Implements just enough of the JSON-RPC 2.0 MCP spec to let
``tests/integration/test_phase13_mcp_subprocess.py`` exercise
``StdioMCPClient`` end-to-end against a real OS subprocess:

* ``initialize`` → returns a scripted ``serverInfo`` / ``capabilities``
* ``tools/list`` → returns a fixed pair of tools
* ``tools/call`` → echoes back the call arguments so the test can assert
  the request round-tripped through stdin/stdout correctly
* anything else → ``-32601 method not found``

Runnable as ``python tests/fixtures/fake_mcp_server.py``. Not importable
at test-collection time (no pytest collection attempts on this file
because the pytest config excludes ``tests/fixtures``).
"""
from __future__ import annotations

import json
import sys


def _reply(rpc_id, result=None, error=None):
    msg: dict = {"jsonrpc": "2.0", "id": rpc_id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method")
        rpc_id = req.get("id")

        # Notifications (no id) — never reply.
        if rpc_id is None:
            continue

        if method == "initialize":
            _reply(rpc_id, result={
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "aim-fake-mcp", "version": "0.0.1"},
            })
        elif method == "tools/list":
            _reply(rpc_id, result={
                "tools": [
                    {
                        "name": "echo",
                        "description": "Echo back the provided arguments.",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "add",
                        "description": "Sum two integers.",
                        "inputSchema": {"type": "object"},
                    },
                ],
            })
        elif method == "tools/call":
            args = (req.get("params") or {}).get("arguments") or {}
            name = (req.get("params") or {}).get("name")
            if name == "echo":
                _reply(rpc_id, result={
                    "content": [{"type": "text", "text": json.dumps(args)}],
                    "isError": False,
                })
            elif name == "add":
                try:
                    total = int(args.get("a", 0)) + int(args.get("b", 0))
                except (TypeError, ValueError):
                    _reply(rpc_id, error={"code": -32602, "message": "invalid arguments"})
                    continue
                _reply(rpc_id, result={
                    "content": [{"type": "text", "text": str(total)}],
                    "isError": False,
                })
            else:
                _reply(rpc_id, error={"code": -32601, "message": f"unknown tool: {name}"})
        else:
            _reply(rpc_id, error={"code": -32601, "message": f"method not found: {method}"})

    return 0


if __name__ == "__main__":
    sys.exit(main())
