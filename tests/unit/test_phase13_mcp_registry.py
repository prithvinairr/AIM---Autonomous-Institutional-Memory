"""Phase 13 — `MCPProviderRegistry` extracted from the MCPHandler god node.

The registry is the part of MCPHandler that tracks provider-class overrides
(for test stubs and operator-registered custom providers). Extracting it
isolates a stable surface that doesn't depend on transport or capability
negotiation — smaller unit, simpler to reason about.

Backward-compat invariant pinned by these tests: the classmethod surface on
MCPHandler (`register`, `unregister`, `reset_registry`, `_provider_registry`)
must keep working exactly as before — all existing tests depend on it.
"""
from __future__ import annotations

import pytest

from aim.mcp.handler import MCPHandler
from aim.mcp.registry import MCPProviderRegistry
from aim.schemas.mcp import MCPProviderType


def _fake_provider_class(ptype: MCPProviderType):
    """Build a minimal MCPProvider-compatible class."""
    class _Fake:
        provider_type = ptype

        async def fetch(self, request):  # pragma: no cover — not invoked here
            return []

        async def health_check(self):  # pragma: no cover
            return True
    _Fake.__name__ = f"Fake{ptype.value.title()}"
    return _Fake


class TestRegistryBasics:
    def setup_method(self):
        self.reg = MCPProviderRegistry()

    def test_empty_on_construction(self):
        assert self.reg.as_dict() == {}
        assert self.reg.is_empty() is True

    def test_register_stores_class(self):
        cls = _fake_provider_class(MCPProviderType.SLACK)
        self.reg.register(cls)
        assert self.reg.as_dict()[MCPProviderType.SLACK] is cls
        assert self.reg.is_empty() is False

    def test_register_last_wins(self):
        """Two providers claiming the same type — the later registration
        overrides the earlier one. Needed for test stubs + operator overrides."""
        cls_a = _fake_provider_class(MCPProviderType.SLACK)
        cls_b = _fake_provider_class(MCPProviderType.SLACK)
        self.reg.register(cls_a)
        self.reg.register(cls_b)
        assert self.reg.as_dict()[MCPProviderType.SLACK] is cls_b

    def test_unregister_removes_class(self):
        cls = _fake_provider_class(MCPProviderType.JIRA)
        self.reg.register(cls)
        self.reg.unregister(MCPProviderType.JIRA)
        assert MCPProviderType.JIRA not in self.reg.as_dict()

    def test_unregister_missing_is_noop(self):
        self.reg.unregister(MCPProviderType.SLACK)  # must not raise
        assert self.reg.as_dict() == {}

    def test_reset_clears_all(self):
        self.reg.register(_fake_provider_class(MCPProviderType.SLACK))
        self.reg.register(_fake_provider_class(MCPProviderType.JIRA))
        self.reg.reset()
        assert self.reg.as_dict() == {}

    def test_register_requires_provider_type_attribute(self):
        """Defensive: a class without ``provider_type`` is a caller bug.
        Registry must raise rather than store a broken entry."""
        class _NoType:
            pass
        with pytest.raises((AttributeError, TypeError)):
            self.reg.register(_NoType)


class TestMCPHandlerFacadePreservedSurface:
    """The existing MCPHandler classmethod surface keeps working post-extraction.

    Existing tests (test_mcp_handler.py, test_mcp_capabilities.py, conftest)
    call MCPHandler.register / .unregister / .reset_registry and inspect
    ._provider_registry directly. Those must still work.
    """

    def setup_method(self):
        MCPHandler.reset_registry()

    def teardown_method(self):
        MCPHandler.reset_registry()

    def test_register_via_handler_classmethod(self):
        cls = _fake_provider_class(MCPProviderType.SLACK)
        MCPHandler.register(cls)
        assert MCPProviderType.SLACK in MCPHandler._provider_registry
        assert MCPHandler._provider_registry[MCPProviderType.SLACK] is cls

    def test_unregister_via_handler_classmethod(self):
        cls = _fake_provider_class(MCPProviderType.JIRA)
        MCPHandler.register(cls)
        MCPHandler.unregister(MCPProviderType.JIRA)
        assert MCPProviderType.JIRA not in MCPHandler._provider_registry

    def test_reset_registry_via_handler_classmethod(self):
        MCPHandler.register(_fake_provider_class(MCPProviderType.SLACK))
        MCPHandler.register(_fake_provider_class(MCPProviderType.JIRA))
        MCPHandler.reset_registry()
        assert MCPHandler._provider_registry == {}

    def test_handler_constructor_reads_from_registry(self):
        """Post-extraction, the MCPHandler constructor must still pick up
        registered provider classes and instantiate them."""
        fake_slack = _fake_provider_class(MCPProviderType.SLACK)
        fake_jira = _fake_provider_class(MCPProviderType.JIRA)
        MCPHandler.register(fake_slack)
        MCPHandler.register(fake_jira)

        handler = MCPHandler()
        assert MCPProviderType.SLACK in handler._providers
        assert MCPProviderType.JIRA in handler._providers
        assert isinstance(handler._providers[MCPProviderType.SLACK], fake_slack)
