"""Phase 14 — Causal Lineage UI polish (backend contract).

Pins the data contract the frontend needs to highlight violating edges:

  1. ``_build_temporal_chain`` returns a list of violating ``rel_id`` values
     (not just a count).
  2. ``ProvenanceMap.violating_edge_ids`` carries those IDs through to the
     wire format so the 3D nebula can render them red.
  3. The IDs come from ``GraphRelationship.rel_id`` — stable identifiers
     the frontend already has on ``graph_edges``.
"""
from __future__ import annotations

from uuid import uuid4

from aim.agents.nodes.synthesizer import _build_temporal_chain
from aim.agents.state import AgentState
from aim.schemas.provenance import ProvenanceMap
from tests.fixtures.adversarial_seed import time_violation_seed


def test_temporal_chain_returns_violating_rel_ids():
    """_build_temporal_chain must expose *which* edges failed the integrity
    check — a plain count is useless to the UI highlighter."""
    sources, relationships = time_violation_seed()
    state = AgentState(
        query_id=uuid4(),
        original_query="Q",
        sources=sources,
        graph_relationships=relationships,
    )

    result = _build_temporal_chain(sources, state)
    # New contract: 3-tuple (events, direction_violations, violating_edge_ids)
    assert len(result) == 3, (
        "_build_temporal_chain must return (events, count, violating_ids) — "
        "the frontend needs specific IDs to highlight."
    )
    _events, count, violating_ids = result

    assert count >= 1
    assert isinstance(violating_ids, list)
    assert "rel-violation-1" in violating_ids, (
        f"Expected the seeded violating rel_id to surface in violating_ids, "
        f"got {violating_ids}"
    )


def test_provenance_map_carries_violating_edge_ids():
    """ProvenanceMap must have ``violating_edge_ids`` so the wire format
    reaches the frontend."""
    # Construct directly — proves the field exists and round-trips.
    pm = ProvenanceMap(
        query_id=uuid4(),
        overall_confidence=0.5,
        violating_edge_ids=["rel-violation-1", "rel-violation-2"],
    )
    assert pm.violating_edge_ids == ["rel-violation-1", "rel-violation-2"]

    # Round-trip through JSON to confirm the field is part of the public schema.
    round_tripped = ProvenanceMap.model_validate_json(pm.model_dump_json())
    assert round_tripped.violating_edge_ids == ["rel-violation-1", "rel-violation-2"]


def test_provenance_map_default_violating_edges_empty():
    """Clean queries must default to an empty list (not None) so the UI can
    safely iterate without null-checks."""
    pm = ProvenanceMap(query_id=uuid4(), overall_confidence=0.5)
    assert pm.violating_edge_ids == []
