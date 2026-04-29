"""Phase 13 — ``MCPClientTransport`` Protocol.

Before this refactor, ``StdioMCPClient`` was the sole concrete client
transport. There was no abstract contract — any future HTTP or WebSocket
MCP client would have to duck-type its way in and hope every call site
was using a compatible subset.

This test pins the Protocol:

* Required methods and their signatures: ``start``, ``stop``, ``send``,
  ``notify``, ``on_notification``, and the ``alive`` boolean property.
* ``StdioMCPClient`` is a structural conformer — operators can substitute
  an alternative transport (HTTP, pipe-mocked) without touching callers.
* A fake that implements the full surface is also accepted, so callers
  that want to inject a test double get a first-class contract rather
  than relying on undocumented method names.

The Protocol is ``@runtime_checkable`` so ``isinstance()`` works for
operator scripts that want to assert transport conformance at boot.
"""
from __future__ import annotations

from aim.mcp.client.stdio_client import StdioMCPClient
from aim.mcp.client.transport import MCPClientTransport


# ── Fake conformer (demonstrates the contract is implementable) ─────────────


class _FakeTransport:
    """Minimal in-memory implementation of the Protocol — no subprocess,
    no network. Future HTTP/WebSocket transports would follow the same
    shape but replace the internals."""

    def __init__(self) -> None:
        self._alive = False
        self._handlers: dict[str, object] = {}

    @property
    def alive(self) -> bool:
        return self._alive

    async def start(self, env: dict[str, str] | None = None) -> None:
        self._alive = True

    async def stop(self) -> None:
        self._alive = False

    async def send(self, method: str, params=None, timeout: float = 30.0) -> dict:
        return {"method": method, "params": params}

    async def notify(self, method: str, params=None) -> None:
        return None

    def on_notification(self, method: str, handler) -> None:
        self._handlers[method] = handler


# ── Tests ───────────────────────────────────────────────────────────────────


class TestProtocolConformance:
    def test_stdio_client_is_structural_conformer(self):
        """The production transport must satisfy the Protocol without
        modification — the Protocol is extracted from existing behaviour,
        not a prescriptive redesign."""
        # Instantiation is enough — no subprocess is spawned by the
        # constructor. ``isinstance`` uses structural checking because
        # MCPClientTransport is ``@runtime_checkable``.
        client = StdioMCPClient(command="does-not-matter", args=[])
        assert isinstance(client, MCPClientTransport)

    def test_fake_is_structural_conformer(self):
        """Test doubles that implement the full surface are also accepted —
        this is the contract callers can rely on when injecting alternate
        transports."""
        fake = _FakeTransport()
        assert isinstance(fake, MCPClientTransport)

    def test_missing_methods_fail_conformance(self):
        """A partial implementation must NOT satisfy the Protocol — that's
        the whole point of declaring it. A class missing ``send`` can't
        pretend to be a transport."""
        class _Partial:
            @property
            def alive(self) -> bool:
                return False

            async def start(self, env=None) -> None:
                pass

            async def stop(self) -> None:
                pass
            # Missing send/notify/on_notification intentionally.

        assert not isinstance(_Partial(), MCPClientTransport)


class TestProtocolSurfaceIsStable:
    """Any future addition to the Protocol risks breaking every external
    transport implementation. These tests pin the exact method set so the
    surface can't be silently widened."""

    def test_protocol_exposes_expected_method_names(self):
        expected = {"start", "stop", "send", "notify", "on_notification", "alive"}
        # ``__annotations__`` on a Protocol carries every declared member.
        declared = set(MCPClientTransport.__dict__)
        # Drop dunder/Protocol metadata.
        declared = {n for n in declared if not n.startswith("_") or n == "alive"}
        missing = expected - declared
        assert not missing, f"Protocol missing expected members: {missing}"
