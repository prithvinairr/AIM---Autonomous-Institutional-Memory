"""MCP Provider Registry — extracted from MCPHandler in Phase 13.

Tracks which provider class answers for each ``MCPProviderType``. Keeping
this separate from MCPHandler shrinks the handler's surface area and makes
registry semantics independently testable (no transport, no capability
negotiation, no dispatch).

Backward-compat: ``MCPHandler`` retains its classmethod surface
(``register``/``unregister``/``reset_registry``/``_provider_registry``) as a
thin facade that delegates to a module-level shared registry. Existing tests
and callers see no API change.
"""
from __future__ import annotations

import structlog

from aim.schemas.mcp import MCPProviderType

log = structlog.get_logger(__name__)


class MCPProviderRegistry:
    """Mutable mapping of ``MCPProviderType`` → provider class.

    Stores classes (not instances) so MCPHandler can instantiate one per
    ``__init__`` call — matching the pre-Phase-13 semantics where each
    handler gets fresh provider instances.
    """

    def __init__(self) -> None:
        self._store: dict[MCPProviderType, type] = {}

    def register(self, provider_class: type) -> type:
        """Add a provider class. Usable as a decorator.

        The class must expose a ``provider_type`` class attribute. Last
        registration wins for a given ``provider_type`` so operators and
        tests can override built-in providers.
        """
        ptype = getattr(provider_class, "provider_type", None)
        if ptype is None:
            raise AttributeError(
                f"{provider_class.__name__} is missing the required "
                "'provider_type' class attribute"
            )
        if not isinstance(ptype, MCPProviderType):
            raise TypeError(
                f"{provider_class.__name__}.provider_type must be MCPProviderType, "
                f"got {type(ptype).__name__}"
            )
        self._store[ptype] = provider_class
        log.info(
            "mcp_registry.provider_registered",
            provider=str(ptype),
            cls=provider_class.__name__,
        )
        return provider_class

    def unregister(self, provider_type: MCPProviderType) -> None:
        """Remove a provider. No-op if the type was never registered."""
        self._store.pop(provider_type, None)

    def reset(self) -> None:
        """Clear all registrations — primarily for test isolation."""
        self._store.clear()

    def as_dict(self) -> dict[MCPProviderType, type]:
        """Return a live view of the registry.

        Exposed for the MCPHandler facade's ``_provider_registry`` attribute,
        which existing tests read directly.
        """
        return self._store

    def is_empty(self) -> bool:
        return not self._store


# Module-level shared registry — MCPHandler's classmethod facade delegates here.
_shared_registry = MCPProviderRegistry()


def get_shared_registry() -> MCPProviderRegistry:
    return _shared_registry
