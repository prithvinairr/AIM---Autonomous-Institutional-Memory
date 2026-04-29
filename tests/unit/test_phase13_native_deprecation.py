"""Phase 13 — ``mcp_transport="native"`` is deprecated.

The native transport path calls provider libraries in-process without going
through MCP JSON-RPC — useful for bootstrapping but not aligned with the
MCP spec. Phase 13 flags it as deprecated so operators get a heads-up before
it's removed.

These tests pin: (a) selecting ``native`` invokes ``log.warning`` with the
``mcp.native_transport_deprecated`` event, (b) ``jsonrpc`` / ``stdio`` don't
log that event.

The tests monkeypatch the handler module's ``log.warning`` rather than
capturing stdout — structlog's output routing can be reconfigured by other
tests in the suite, but the logger identity is stable.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aim.mcp import handler as handler_mod
from aim.mcp.handler import warn_if_transport_deprecated


@pytest.fixture
def mock_log(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(handler_mod, "log", fake)
    return fake


class TestNativeDeprecationWarning:
    def test_native_transport_emits_deprecation_log(self, mock_log):
        warn_if_transport_deprecated("native")
        # Exactly one call, and the event name is the one operators will grep for.
        assert mock_log.warning.call_count == 1
        args, kwargs = mock_log.warning.call_args
        assert args[0] == "mcp.native_transport_deprecated"
        assert kwargs.get("transport") == "native"
        # Actionable guidance must be included so operators know what to switch to.
        assert "stdio" in kwargs.get("recommendation", "")

    def test_stdio_transport_does_not_warn(self, mock_log):
        warn_if_transport_deprecated("stdio")
        assert mock_log.warning.call_count == 0

    def test_jsonrpc_transport_does_not_warn(self, mock_log):
        warn_if_transport_deprecated("jsonrpc")
        assert mock_log.warning.call_count == 0

    def test_unknown_transport_does_not_warn(self, mock_log):
        """The Settings validator already rejects unknown values. The
        deprecation check must not double-report for values that are
        already rejected upstream."""
        warn_if_transport_deprecated("bogus")
        assert mock_log.warning.call_count == 0
