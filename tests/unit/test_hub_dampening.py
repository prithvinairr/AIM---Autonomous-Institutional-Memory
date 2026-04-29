"""Tests for hub-node dampening in graph traversal."""
from __future__ import annotations

import pytest

from aim.graph.queries import (
    EXPAND_NEIGHBOURHOOD,
    EXPAND_NEIGHBOURHOOD_DAMPENED,
    EXPAND_NEIGHBOURHOOD_FILTERED,
)


# ── Query template validation ────────────────────────────────────────────────

class TestDampenedQuery:
    def test_dampened_query_contains_degree_filter(self):
        """The dampened query must filter nodes by degree."""
        assert "degree <= $max_degree" in EXPAND_NEIGHBOURHOOD_DAMPENED

    def test_dampened_query_preserves_root_nodes(self):
        """Root nodes should never be filtered even if they exceed max_degree."""
        assert "elementId(n) IN root_ids" in EXPAND_NEIGHBOURHOOD_DAMPENED

    def test_dampened_query_has_relationship_filter(self):
        """Dampened query must support relationship type filtering."""
        assert "$rel_filter" in EXPAND_NEIGHBOURHOOD_DAMPENED

    def test_dampened_query_has_depth_param(self):
        assert "$depth" in EXPAND_NEIGHBOURHOOD_DAMPENED

    def test_dampened_query_has_entity_ids_param(self):
        assert "$entity_ids" in EXPAND_NEIGHBOURHOOD_DAMPENED

    def test_dampened_query_returns_standard_columns(self):
        """Must return the same columns as the standard query."""
        for col in ["rel_id", "rel_type", "source_id", "target_id", "properties"]:
            assert col in EXPAND_NEIGHBOURHOOD_DAMPENED

    def test_dampened_query_filters_relationships_by_kept_nodes(self):
        """Relationships should be filtered to only connect kept (non-hub) nodes."""
        assert "startNode(r) IN kept" in EXPAND_NEIGHBOURHOOD_DAMPENED
        assert "endNode(r) IN kept" in EXPAND_NEIGHBOURHOOD_DAMPENED


class TestBidirectionalExpansion:
    def test_standard_expansion_is_bidirectional(self):
        """EXPAND_NEIGHBOURHOOD should NOT restrict to outgoing only."""
        # The old query had "relationshipFilter: '>'" — ensure it's gone
        assert "relationshipFilter: '>'" not in EXPAND_NEIGHBOURHOOD

    def test_filtered_expansion_uses_param(self):
        """EXPAND_NEIGHBOURHOOD_FILTERED should use $rel_filter parameter."""
        assert "$rel_filter" in EXPAND_NEIGHBOURHOOD_FILTERED


# ── Intent filter direction tests ────────────────────────────────────────────

class TestIntentFilters:
    def test_ownership_is_bidirectional(self):
        from aim.agents.nodes.graph_searcher import _INTENT_REL_FILTERS
        filt = _INTENT_REL_FILTERS["ownership"]
        assert not filt.endswith(">"), "Ownership should be bidirectional"

    def test_dependency_is_outgoing(self):
        from aim.agents.nodes.graph_searcher import _INTENT_REL_FILTERS
        filt = _INTENT_REL_FILTERS["dependency"]
        assert filt.endswith(">"), "Dependency should be outgoing only"

    def test_incident_is_bidirectional(self):
        from aim.agents.nodes.graph_searcher import _INTENT_REL_FILTERS
        filt = _INTENT_REL_FILTERS["incident"]
        assert not filt.endswith(">"), "Incident should be bidirectional"

    def test_decision_is_bidirectional(self):
        from aim.agents.nodes.graph_searcher import _INTENT_REL_FILTERS
        filt = _INTENT_REL_FILTERS["decision"]
        assert not filt.endswith(">"), "Decision should be bidirectional"

    def test_temporal_is_bidirectional(self):
        from aim.agents.nodes.graph_searcher import _INTENT_REL_FILTERS
        filt = _INTENT_REL_FILTERS["temporal"]
        assert not filt.endswith(">"), "Temporal should be bidirectional"

    def test_general_is_bidirectional(self):
        from aim.agents.nodes.graph_searcher import _INTENT_REL_FILTERS
        filt = _INTENT_REL_FILTERS["general"]
        assert filt == "", "General should be empty (all directions)"

    def test_all_intents_present(self):
        from aim.agents.nodes.graph_searcher import _INTENT_REL_FILTERS
        expected = {"ownership", "dependency", "incident", "decision", "temporal", "general"}
        assert set(_INTENT_REL_FILTERS.keys()) == expected


# ── Config validation ────────────────────────────────────────────────────────

class TestHubDegreeConfig:
    def test_default_value(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        from aim.config import Settings
        s = Settings()
        assert s.graph_hub_degree_limit == 25

    def test_min_value(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("GRAPH_HUB_DEGREE_LIMIT", "5")
        from aim.config import Settings
        s = Settings()
        assert s.graph_hub_degree_limit == 5

    def test_rejects_below_min(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("GRAPH_HUB_DEGREE_LIMIT", "2")
        from aim.config import Settings
        with pytest.raises(Exception):
            Settings()
