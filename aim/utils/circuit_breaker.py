"""Circuit breaker — prevents cascading failures on downstream services.

States:
  CLOSED   → normal operation; failures increment counter
  OPEN     → service is assumed down; all calls rejected immediately
  HALF_OPEN → grace period; one test call allowed to probe recovery
"""
from __future__ import annotations

import asyncio
import time
from enum import StrEnum
from typing import Any, Callable, Coroutine, TypeVar

import structlog

log = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a call is rejected because the circuit is OPEN."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Circuit '{name}' is OPEN — service unavailable")
        self.service_name = name


class CircuitBreaker:
    """Async-safe circuit breaker for one downstream service."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
    ) -> None:
        self.name = name
        self._threshold = failure_threshold
        self._reset_timeout = reset_timeout

        self._failures = 0
        self._last_failure_time: float = 0.0
        self._state = CircuitState.CLOSED
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._reset_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    async def call(
        self,
        coro_fn: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        is_probe = False
        async with self._lock:
            current = self.state
            if current == CircuitState.OPEN:
                log.warning("circuit_breaker.rejected", name=self.name, state=current)
                raise CircuitOpenError(self.name)
            if current == CircuitState.HALF_OPEN:
                is_probe = True
                log.info(
                    "circuit_breaker.half_open",
                    name=self.name,
                    msg="Allowing single probe call to test recovery",
                )
                # Block other callers while the probe is in flight.
                # The lock is released before await coro_fn(), so without this
                # every concurrent caller would also enter HALF_OPEN and all
                # become simultaneous probe calls — defeating the purpose.
                self._state = CircuitState.OPEN

        try:
            result: T = await coro_fn(*args, **kwargs)
        except CircuitOpenError:
            raise
        except BaseException as exc:
            # BaseException catches CancelledError too — prevents the circuit
            # from getting wedged in OPEN when a probe is cancelled externally.
            await self._on_failure(exc)
            raise
        else:
            await self._on_success()
            return result

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                log.info("circuit_breaker.closed", name=self.name)
            self._state = CircuitState.CLOSED
            self._failures = 0

    async def _on_failure(self, exc: BaseException) -> None:
        async with self._lock:
            self._failures += 1
            self._last_failure_time = time.monotonic()
            if self._state == CircuitState.OPEN:
                # Probe failed — stays OPEN with refreshed timer so the
                # reset_timeout restarts from now, not the original failure.
                log.warning(
                    "circuit_breaker.probe_failed",
                    name=self.name,
                    error=type(exc).__name__,
                )
            elif self._failures >= self._threshold and self._state == CircuitState.CLOSED:
                self._state = CircuitState.OPEN
                log.error(
                    "circuit_breaker.opened",
                    name=self.name,
                    failures=self._failures,
                    error=str(exc),
                )

    def reset(self) -> None:
        """Force circuit back to CLOSED (for testing / manual recovery)."""
        self._state = CircuitState.CLOSED
        self._failures = 0

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failures": self._failures,
            "threshold": self._threshold,
            "reset_timeout_seconds": self._reset_timeout,
        }


# ── Global registry ───────────────────────────────────────────────────────────

_registry: dict[str, CircuitBreaker] = {}


def get_breaker(name: str) -> CircuitBreaker:
    """Return the named circuit breaker, creating it lazily from settings.

    Safe without an async lock: asyncio uses a single-threaded event loop, so
    the check-then-set is atomic with respect to other coroutines.
    ``dict.setdefault`` is used for clarity and to make the intent explicit.
    """
    if name not in _registry:
        from aim.config import get_settings

        s = get_settings()
        _registry.setdefault(
            name,
            CircuitBreaker(
                name=name,
                failure_threshold=s.circuit_breaker_threshold,
                reset_timeout=s.circuit_breaker_reset_seconds,
            ),
        )
    return _registry[name]


def all_statuses() -> list[dict[str, Any]]:
    return [b.status() for b in _registry.values()]
