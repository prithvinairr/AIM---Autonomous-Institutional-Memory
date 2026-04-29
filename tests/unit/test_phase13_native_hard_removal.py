"""Phase 13 — ``mcp_transport="native"`` is removed, not merely deprecated.

The earlier Phase 13 pass (``test_phase13_native_deprecation.py``) emitted
a log warning when operators selected ``native`` at startup. That was a
soft landing — the config still accepted the value and providers still
dispatched through the REST fallback branch.

Now ``native`` is rejected at config-validation time. Picking it is a
``ValidationError``, not a warning. The intent is to force operators onto
``stdio`` (the spec transport) or ``jsonrpc`` (reserved for the future
HTTP client) so there's no path under which a caller can silently bypass
the MCP JSON-RPC handshake.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from aim.config import Settings


class TestNativeRejectedAtValidation:
    def test_native_transport_raises_validation_error(self):
        with pytest.raises(ValidationError) as excinfo:
            Settings(mcp_transport="native")
        # The message must name both the rejected value and the allowed
        # set so operators know what to switch to.
        msg = str(excinfo.value).lower()
        assert "mcp_transport" in msg
        assert "stdio" in msg or "jsonrpc" in msg

    def test_stdio_is_still_accepted(self):
        # Smoke: the valid default still passes validation.
        s = Settings(mcp_transport="stdio")
        assert s.mcp_transport == "stdio"

    def test_jsonrpc_is_still_accepted(self):
        """jsonrpc remains a reserved-but-legal value — a future HTTP
        client transport will dispatch through it. Removing it here would
        break operator configs that pre-declared it."""
        s = Settings(mcp_transport="jsonrpc")
        assert s.mcp_transport == "jsonrpc"

    def test_unknown_transport_still_rejected(self):
        with pytest.raises(ValidationError):
            Settings(mcp_transport="bogus")
