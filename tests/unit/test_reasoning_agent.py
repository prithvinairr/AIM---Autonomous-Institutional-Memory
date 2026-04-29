"""Unit tests for reasoning agent cost computation and token metrics."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from aim.agents.reasoning_agent import _compute_cost


def _mock_settings(**overrides):
    defaults = {
        "llm_input_cost_per_mtok": 15.0,
        "llm_output_cost_per_mtok": 75.0,
        "embedding_cost_per_mtok": 0.02,
        "embedding_model": "text-embedding-3-small",
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def test_compute_cost_basic():
    with patch("aim.config.get_settings", return_value=_mock_settings()):
        cost = _compute_cost(input_tokens=1000, output_tokens=500, embedding_tokens=200)

    # input: 1000 * 15/1M = 0.015
    # output: 500 * 75/1M = 0.0375
    # embedding: 200 * 0.02/1M = 0.000004
    assert cost.input_tokens == 1000
    assert cost.output_tokens == 500
    assert cost.embedding_tokens == 200
    expected = round(0.015 + 0.0375 + 0.000004, 6)
    assert cost.estimated_cost_usd == expected


def test_compute_cost_zero_tokens():
    with patch("aim.config.get_settings", return_value=_mock_settings()):
        cost = _compute_cost(0, 0, 0)

    assert cost.estimated_cost_usd == 0.0
    assert cost.input_tokens == 0


def test_compute_cost_custom_pricing():
    settings = _mock_settings(
        llm_input_cost_per_mtok=10.0,
        llm_output_cost_per_mtok=30.0,
        embedding_cost_per_mtok=0.01,
    )
    with patch("aim.config.get_settings", return_value=settings):
        cost = _compute_cost(1_000_000, 1_000_000, 1_000_000)

    # input: 1M * 10/1M = 10.0
    # output: 1M * 30/1M = 30.0
    # embedding: 1M * 0.01/1M = 0.01
    assert cost.estimated_cost_usd == round(10.0 + 30.0 + 0.01, 6)


def test_compute_cost_large_token_counts():
    with patch("aim.config.get_settings", return_value=_mock_settings()):
        cost = _compute_cost(50000, 10000, 5000)

    assert cost.estimated_cost_usd > 0
    assert cost.input_tokens == 50000
    assert cost.output_tokens == 10000
    assert cost.embedding_tokens == 5000


def test_compute_cost_only_embeddings():
    with patch("aim.config.get_settings", return_value=_mock_settings()):
        cost = _compute_cost(0, 0, 1_000_000)

    # Only embedding: 1M * 0.02/1M = 0.02
    assert cost.estimated_cost_usd == 0.02
    assert cost.input_tokens == 0
    assert cost.output_tokens == 0
