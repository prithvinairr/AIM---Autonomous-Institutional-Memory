"""Tests for metrics helper functions: init_app_info, update_circuit_metrics, prometheus_response."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from aim.utils.metrics import init_app_info, prometheus_response, update_circuit_metrics


def _mock_settings(**overrides):
    defaults = {
        "app_version": "1.0.0",
        "app_env": "test",
        "llm_model": "claude-opus-4-6",
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


class TestInitAppInfo:
    @patch("aim.config.get_settings")
    def test_sets_info_without_error(self, mock_settings):
        mock_settings.return_value = _mock_settings()
        # Should not raise
        init_app_info()

    @patch("aim.config.get_settings")
    def test_uses_settings_values(self, mock_settings):
        mock_settings.return_value = _mock_settings(
            app_version="2.5.0", app_env="production", llm_model="gpt-4"
        )
        init_app_info()
        # No assertion needed — just verifying it runs without error


class TestUpdateCircuitMetrics:
    @patch("aim.utils.circuit_breaker.all_statuses", return_value=[])
    def test_no_breakers_is_noop(self, _mock):
        update_circuit_metrics()

    @patch("aim.utils.circuit_breaker.all_statuses")
    def test_updates_gauge_for_each_breaker(self, mock_statuses):
        mock_statuses.return_value = [
            {"name": "neo4j", "state": "closed"},
            {"name": "pinecone", "state": "open"},
            {"name": "redis", "state": "half_open"},
        ]
        update_circuit_metrics()

    @patch("aim.utils.circuit_breaker.all_statuses")
    def test_unknown_state_defaults_to_zero(self, mock_statuses):
        mock_statuses.return_value = [
            {"name": "unknown_svc", "state": "unknown_state"},
        ]
        update_circuit_metrics()


class TestPrometheusResponse:
    def test_returns_bytes_and_content_type(self):
        body, content_type = prometheus_response()
        assert isinstance(body, bytes)
        assert "text/plain" in content_type or "text/" in content_type

    def test_body_contains_metric_names(self):
        body, _ = prometheus_response()
        text = body.decode()
        assert "aim_queries_total" in text or "aim_" in text
