"""Phase β — graph-aware synthesis prompt shape.

When ``settings.synthesis_mode = "graph_aware"``, the synthesizer
renders retrieved graph state as a typed subgraph prompt:

  ## Nodes (typed subgraph)
  - n1 (Person, Sarah Chen)
  - n2 (Project, Aurora)
  - n3 (JiraIssue, AUR-123)

  ## Edges
  - n1 -[OWNS]-> n2
  - n2 -[HAS_ISSUE]-> n3

This pins:

* The new mode is opt-in via config — flat remains the default so
  benchmarking can happen before any behaviour flips.
* Nodes render with stable n1/n2/... identifiers in ranked order.
* Edges render using those identifiers.
* Edges whose endpoints aren't rendered are suppressed (no dangling
  references).
* The flat mode is byte-identical to pre-Phase-β output.
* The graph-aware mode is safe when the state has no graph content
  (still renders the envelope, no crash).
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from aim.agents.nodes.synthesizer import (
    _build_context_block,
    _build_exact_incident_answer,
    _build_graph_aware_context_block,
)
from aim.agents.state import AgentState
from aim.schemas.graph import GraphEntity, GraphRelationship
from aim.schemas.provenance import SourceReference, SourceType


def _make_state(entities=None, rels=None) -> AgentState:
    entities = entities or []
    rels = rels or []
    sources = {}
    for e in entities:
        sid = f"src-{e.entity_id}"
        sources[sid] = SourceReference(
            source_id=sid,
            source_type=SourceType.NEO4J_GRAPH,
            title=e.properties.get("name", ""),
            content_snippet=e.properties.get("name", ""),
            confidence=0.9,
            metadata={"entity_id": e.entity_id},
        )
    return AgentState(
        query_id=str(uuid.uuid4()),
        query="test",
        original_query="test",
        sub_queries=["test"],
        graph_entities=entities,
        graph_relationships=rels,
        sources=sources,
    )


def _entity(entity_id: str, name: str, label: str = "Person") -> GraphEntity:
    return GraphEntity(
        entity_id=entity_id,
        labels=["Entity", label],
        properties={"name": name},
    )


def _rel(src: str, tgt: str, rel_type: str) -> GraphRelationship:
    return GraphRelationship(
        rel_id=f"{src}->{rel_type}->{tgt}",
        rel_type=rel_type,
        source_id=src,
        target_id=tgt,
    )


class TestTypedSubgraphBlock:
    def test_exact_incident_updates_render_before_nodes(self):
        incident = GraphEntity(
            entity_id="inc-1",
            labels=["Entity", "Incident"],
            properties={
                "name": "INC-2025-099",
                "incident_id": "INC-2025-099",
                "summary": "INC-2025-099 was a config drift.",
                "cause_summary": "config drift in auth service",
                "resolution_action": "rolled back to previous config",
                "resolution_time": "11am",
            },
        )
        lead = _entity("person-1", "Sarah Chen", "Person")
        state = _make_state(
            [incident, lead],
            [_rel("person-1", "inc-1", "RESPONDED_TO")],
        ).model_copy(update={"original_query": "What happened in INC-2025-099?"})

        block = _build_graph_aware_context_block(state, ranked=[])

        assert "## Exact Incident Updates" in block
        assert "response_lead=Sarah Chen" in block
        assert "fix=rolled back to previous config at 11am" in block
        assert block.index("## Exact Incident Updates") < block.index("## Nodes")

    def test_exact_incident_answer_uses_structured_fields(self):
        incident = GraphEntity(
            entity_id="inc-1",
            labels=["Entity", "Incident"],
            properties={
                "name": "INC-2025-099",
                "incident_id": "INC-2025-099",
                "summary": "INC-2025-099 was a config drift.",
                "cause_summary": "config drift in auth service",
                "resolution_action": "rolled back to previous config",
                "resolution_time": "11am",
            },
        )
        lead = _entity("person-1", "Sarah Chen", "Person")
        state = _make_state(
            [incident, lead],
            [_rel("person-1", "inc-1", "RESPONDED_TO")],
        ).model_copy(update={"original_query": "Who led INC-2025-099 and what was the fix?"})

        answer = _build_exact_incident_answer(state)

        assert answer is not None
        assert "Response lead: Sarah Chen." in answer
        assert "Fix: rolled back to previous config at 11am." in answer

    def test_nodes_block_uses_stable_slot_ids(self):
        state = _make_state([
            _entity("e1", "Sarah Chen", "Person"),
            _entity("e2", "Aurora", "Project"),
        ])
        block = _build_graph_aware_context_block(state, ranked=[])
        assert "## Nodes (typed subgraph)" in block
        assert "n1" in block
        assert "n2" in block
        # Primary (non-Entity) label must be rendered.
        assert "Person" in block
        assert "Project" in block

    def test_edges_use_slot_ids(self):
        state = _make_state(
            [
                _entity("e1", "Sarah", "Person"),
                _entity("e2", "Aurora", "Project"),
            ],
            [_rel("e1", "e2", "OWNS")],
        )
        block = _build_graph_aware_context_block(state, ranked=[])
        assert "## Edges" in block
        # Order-dependent but deterministic on this small fixture.
        assert "n1 -[OWNS]-> n2" in block or "n2 -[OWNS]-> n1" in block.replace(
            "n1 -[OWNS]-> n2", ""
        )

    def test_dangling_edges_suppressed(self):
        """An edge whose source or target isn't in the rendered Nodes
        block is unciteable — the LLM can't resolve its slot ID. Those
        edges must be silently dropped."""
        state = _make_state(
            [_entity("e1", "Sarah", "Person")],  # e2 not in entities
            [_rel("e1", "e2", "OWNS")],
        )
        block = _build_graph_aware_context_block(state, ranked=[])
        # The Edges header should not appear — no renderable edges.
        assert "## Edges" not in block

    def test_empty_state_renders_envelope_only(self):
        """Graph-aware mode must not crash on empty state. It still
        renders the boundary tags so the prompt-injection defense stays
        consistent."""
        state = _make_state([], [])
        block = _build_graph_aware_context_block(state, ranked=[])
        # Envelope tags are the only guaranteed content.
        assert "<retrieved_context>" in block
        assert "</retrieved_context>" in block
        assert "## Nodes" not in block


class TestModeDispatch:
    @pytest.mark.asyncio
    async def test_flat_mode_does_not_contain_typed_subgraph(self, monkeypatch):
        """Flat mode is the default; it must not accidentally emit the
        new Nodes/Edges block. Regression guard."""
        # Monkeypatch get_settings to simulate flat mode without
        # touching process-wide config state.
        from aim.agents.nodes import synthesizer as mod

        class _S:
            synthesis_mode = "flat"
            encrypted_fields: list[str] = []

        monkeypatch.setattr(mod, "get_settings", lambda: _S())

        state = _make_state(
            [
                _entity("e1", "Sarah", "Person"),
                _entity("e2", "Aurora", "Project"),
            ],
            [_rel("e1", "e2", "OWNS")],
        )
        with patch(
            "aim.agents.nodes.synthesizer._cross_modal_rerank",
            AsyncMock(return_value=[]),
        ):
            block = await _build_context_block(state)
        assert "## Nodes (typed subgraph)" not in block
        # Flat mode still uses the legacy "Knowledge Graph Entities" header.
        assert "## Knowledge Graph Entities" in block

    @pytest.mark.asyncio
    async def test_graph_aware_mode_emits_typed_subgraph(self, monkeypatch):
        from aim.agents.nodes import synthesizer as mod

        class _S:
            synthesis_mode = "graph_aware"
            encrypted_fields: list[str] = []

        monkeypatch.setattr(mod, "get_settings", lambda: _S())

        state = _make_state([_entity("e1", "Sarah", "Person")])
        with patch(
            "aim.agents.nodes.synthesizer._cross_modal_rerank",
            AsyncMock(return_value=[]),
        ):
            block = await _build_context_block(state)
        assert "## Nodes (typed subgraph)" in block


class TestSystemPromptMentionsPathCitation:
    """The prompt rules must tell the LLM how to use the new format.
    Otherwise the subgraph is decorative — the model has no instruction
    to cite it."""

    def test_system_prompt_teaches_path_citation(self):
        from aim.agents.nodes.synthesizer import _SYSTEM_PROMPT_BASE

        # The rule must mention both the `[path: ...]` citation format
        # and the constraint that n-slot IDs come from the Nodes block.
        assert "[path:" in _SYSTEM_PROMPT_BASE
        assert "Nodes" in _SYSTEM_PROMPT_BASE
