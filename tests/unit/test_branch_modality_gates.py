"""Phase γ.3 — per-branch modality gates on search nodes.

Pins that ``state.graph_search_enabled`` / ``state.vector_search_enabled``
are honoured by the respective nodes — a branch orchestrator that asks
for a ``graph_only`` recipe must actually get a graph-only pipeline,
not a hybrid wearing a different hat.

These gates replace the prior "three fusion variants" branch palette
that was fan-out over one axis; the new palette is fan-out over
orthogonal retrieval modalities.
"""
from __future__ import annotations

import uuid

import pytest

from aim.agents.nodes.graph_searcher import search_knowledge_graph
from aim.agents.nodes.vector_retriever import retrieve_vectors
from aim.agents.state import AgentState


def _state(
    *,
    graph_on: bool = True,
    vector_on: bool = True,
    sub_queries: list[str] | None = None,
) -> AgentState:
    return AgentState(
        query_id=uuid.uuid4(),
        original_query="q",
        sub_queries=sub_queries if sub_queries is not None else ["q"],
        graph_search_enabled=graph_on,
        vector_search_enabled=vector_on,
    )


class TestGraphSearchGate:
    @pytest.mark.asyncio
    async def test_gate_off_is_noop(self):
        """With ``graph_search_enabled=False`` the node must not touch
        Neo4j at all — not even the breaker. We assert that by running
        the real node; if it tried to connect it would blow up in this
        unit-test environment (no Neo4j)."""
        s = _state(graph_on=False)
        out = await search_knowledge_graph(s)
        # No entities added, no relationships added, nothing crashed.
        assert out.graph_entities == []
        assert out.graph_relationships == []
        # The reason is logged in reasoning_steps for the evaluator.
        assert any("Graph search skipped" in r for r in out.reasoning_steps)

    @pytest.mark.asyncio
    async def test_gate_off_preserves_state(self):
        """The skip must be copy-not-mutate — downstream nodes still see
        whatever was on the state coming in."""
        s = _state(graph_on=False, sub_queries=["alpha", "beta"])
        out = await search_knowledge_graph(s)
        assert out.sub_queries == ["alpha", "beta"]
        assert out.query_id == s.query_id


class TestVectorSearchGate:
    @pytest.mark.asyncio
    async def test_gate_off_is_noop(self):
        s = _state(vector_on=False)
        out = await retrieve_vectors(s)
        assert out.vector_snippets == []
        assert any("Vector search skipped" in r for r in out.reasoning_steps)

    @pytest.mark.asyncio
    async def test_both_gates_off_still_safe(self):
        """Pathological branch: both modalities off. Neither node should
        crash; state flows through with skip notices."""
        s = _state(graph_on=False, vector_on=False)
        s1 = await search_knowledge_graph(s)
        s2 = await retrieve_vectors(s1)
        assert s2.graph_entities == []
        assert s2.vector_snippets == []
        # Both skip messages present.
        steps = " ".join(s2.reasoning_steps)
        assert "Graph search skipped" in steps
        assert "Vector search skipped" in steps


class TestBranchStrategyOrthogonality:
    def test_palette_covers_three_orthogonal_recipes(self):
        """The shipped palette must have one each of hybrid / graph-only
        / vector-only — this is the audit fix. If a future refactor
        reshuffles to a single-axis palette again, this test catches it."""
        from aim.agents.reasoning_agent import _BRANCH_STRATEGIES

        recipes: set[tuple[bool, bool]] = set()
        for _, overrides in _BRANCH_STRATEGIES:
            g = overrides.get("graph_search_enabled", True)
            v = overrides.get("vector_search_enabled", True)
            recipes.add((bool(g), bool(v)))
        assert (True, True) in recipes   # hybrid
        assert (True, False) in recipes  # graph-only
        assert (False, True) in recipes  # vector-only
