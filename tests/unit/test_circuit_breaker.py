"""Unit tests for the async circuit breaker."""
from __future__ import annotations

import asyncio

import pytest

from aim.utils.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


@pytest.fixture
def breaker():
    return CircuitBreaker("test_svc", failure_threshold=3, reset_timeout=60.0)


# ── State transitions ─────────────────────────────────────────────────────────

async def test_initial_state_is_closed(breaker):
    assert breaker.state == CircuitState.CLOSED


async def test_successful_call_returns_value(breaker):
    async def fn():
        return 42

    assert await breaker.call(fn) == 42


async def test_successful_call_does_not_increment_failures(breaker):
    async def fn():
        return "ok"

    await breaker.call(fn)
    assert breaker._failures == 0


async def test_failed_call_increments_failure_count(breaker):
    async def fails():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await breaker.call(fails)

    assert breaker._failures == 1
    assert breaker.state == CircuitState.CLOSED  # not yet at threshold


async def test_opens_after_reaching_threshold(breaker):
    async def fails():
        raise ValueError()

    for _ in range(3):
        with pytest.raises(ValueError):
            await breaker.call(fails)

    assert breaker._state == CircuitState.OPEN


async def test_open_circuit_rejects_subsequent_calls(breaker):
    async def fails():
        raise ValueError()

    for _ in range(3):
        with pytest.raises(ValueError):
            await breaker.call(fails)

    async def should_not_run():
        return "never reached"

    with pytest.raises(CircuitOpenError) as exc_info:
        await breaker.call(should_not_run)

    assert exc_info.value.service_name == "test_svc"


async def test_transitions_to_half_open_after_reset_timeout():
    b = CircuitBreaker("hopen", failure_threshold=1, reset_timeout=0.05)

    async def fails():
        raise ValueError()

    with pytest.raises(ValueError):
        await b.call(fails)

    assert b._state == CircuitState.OPEN

    await asyncio.sleep(0.1)
    assert b.state == CircuitState.HALF_OPEN


async def test_successful_call_in_half_open_closes_circuit():
    b = CircuitBreaker("recover", failure_threshold=1, reset_timeout=0.05)

    async def fails():
        raise ValueError()

    async def succeeds():
        return "recovered"

    with pytest.raises(ValueError):
        await b.call(fails)

    await asyncio.sleep(0.1)
    assert b.state == CircuitState.HALF_OPEN

    result = await b.call(succeeds)
    assert result == "recovered"
    assert b.state == CircuitState.CLOSED
    assert b._failures == 0


async def test_success_after_partial_failures_resets_counter(breaker):
    async def fails():
        raise ValueError()

    async def succeeds():
        return "ok"

    # One failure, then a success — should reset
    with pytest.raises(ValueError):
        await breaker.call(fails)

    assert breaker._failures == 1
    await breaker.call(succeeds)
    assert breaker._failures == 0


# ── Manual reset ──────────────────────────────────────────────────────────────

async def test_manual_reset_closes_open_circuit(breaker):
    async def fails():
        raise ValueError()

    for _ in range(3):
        with pytest.raises(ValueError):
            await breaker.call(fails)

    assert breaker._state == CircuitState.OPEN
    breaker.reset()
    assert breaker.state == CircuitState.CLOSED


# ── Status dict ───────────────────────────────────────────────────────────────

async def test_status_dict_has_expected_keys(breaker):
    s = breaker.status()
    assert s["name"] == "test_svc"
    assert s["state"] == CircuitState.CLOSED.value
    assert s["failures"] == 0
    assert s["threshold"] == 3
    assert "reset_timeout_seconds" in s


async def test_circuit_open_error_message_contains_service_name():
    b = CircuitBreaker("my_svc", failure_threshold=1, reset_timeout=60.0)

    async def fails():
        raise RuntimeError()

    with pytest.raises(RuntimeError):
        await b.call(fails)

    with pytest.raises(CircuitOpenError) as exc_info:
        await b.call(fails)

    assert "my_svc" in str(exc_info.value)
