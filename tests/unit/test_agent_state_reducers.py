"""Pins reducers for LangGraph control-state fields."""
from __future__ import annotations

from aim.agents.state import _latest_value


def test_latest_value_allows_reloop_flag_to_reset() -> None:
    assert _latest_value(True, False) is False

