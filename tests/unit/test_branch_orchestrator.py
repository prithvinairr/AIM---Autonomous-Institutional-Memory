"""Phase γ.2 (wire-in) — branch fan-out orchestrator.

The primitives in ``test_branch_selector.py`` pin the scoring contract;
this file pins the wire-in that spawns N parallel branches, each with a
distinct ``fusion_mode_override``, and picks the winner.

Pinned invariants
-----------------
* ``reasoning_branch_count == 1`` → single compiled-graph invocation (no
  fan-out, no behavioural delta from pre-γ.2).
* ``reasoning_branch_count > 1`` → ``asyncio.gather`` of N branches, each
  carrying a distinct ``fusion_mode_override`` in its initial state.
* Branches whose ainvoke raises are excluded from selection; if *all*
  branches fail, the first exception is re-raised (no silent empty
  answer).
* The winning branch's final state is what the caller sees — scoreboard
  is logged, not swallowed.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from aim.agents import reasoning_agent
from aim.agents.branch_selector import BranchCandidate
from aim.agents.state import AgentState
from aim.schemas.provenance import (
    ProvenanceMap,
    SourceReference,
    SourceType,
)


def _state(
    answer: str = "a" * 300,
    confidence: float = 0.8,
    sources: int = 2,
) -> AgentState:
    qid = uuid.uuid4()
    srcs = {
        f"s{i}": SourceReference(
            source_id=f"s{i}",
            source_type=SourceType.NEO4J_GRAPH,
            title=f"t{i}",
            content_snippet=f"c{i}",
            confidence=0.9,
        )
        for i in range(sources)
    }
    prov = ProvenanceMap(
        query_id=qid,
        sources=srcs,
        overall_confidence=confidence,
    )
    return AgentState(
        query_id=qid,
        original_query="q",
        sub_queries=["q"],
        sources=srcs,
        sub_query_source_map={"q": list(srcs.keys())},
        citation_map={"c1": list(srcs.keys())},
        answer=answer,
        provenance=prov,
    )


class TestCandidateProjection:
    def test_projects_state_into_candidate(self):
        s = _state(answer="hello world" * 20, confidence=0.77, sources=3)
        c = reasoning_agent._candidate_from_state("b0", s)
        assert c.branch_id == "b0"
        assert c.total_sources == 3
        assert c.total_sub_queries == 1
        assert c.covered_sub_queries == 1
        assert c.confidence == pytest.approx(0.77)
        assert c.answer_text.startswith("hello world")

    def test_handles_missing_provenance(self):
        # A pipeline that bailed before synthesis has no provenance —
        # don't crash when scoring it.
        s = AgentState(
            query_id=uuid.uuid4(),
            original_query="q",
        )
        c = reasoning_agent._candidate_from_state("dead", s)
        assert c.confidence == 0.0


class TestRunBranchesAndSelect:
    @pytest.mark.asyncio
    async def test_winner_is_highest_scoring(self):
        # Two branches (hybrid + graph_only): strong graph_only vs weak hybrid.
        strong = _state(answer="a" * 500, confidence=0.95, sources=2)
        weak = _state(answer="tiny", confidence=0.10, sources=0)

        call_count = {"n": 0}

        async def fake_ainvoke(state, config=None):
            call_count["n"] += 1
            # Route by modality: graph_only branch has vector off.
            return strong if not state.vector_search_enabled else weak

        with patch.object(
            reasoning_agent._compiled_graph,
            "ainvoke",
            side_effect=fake_ainvoke,
        ):
            initial = AgentState(query_id=uuid.uuid4(), original_query="q")
            final = await reasoning_agent._run_branches_and_select(
                initial, recursion_limit=50, branch_count=2
            )
        assert call_count["n"] == 2
        assert final.answer == strong.answer

    @pytest.mark.asyncio
    async def test_failed_branches_excluded(self):
        strong = _state(answer="a" * 500, confidence=0.9)

        async def fake_ainvoke(state, config=None):
            # Blow up the hybrid branch (both modalities on); graph_only survives.
            if state.graph_search_enabled and state.vector_search_enabled:
                raise RuntimeError("hybrid blew up")
            return strong

        with patch.object(
            reasoning_agent._compiled_graph,
            "ainvoke",
            side_effect=fake_ainvoke,
        ):
            initial = AgentState(query_id=uuid.uuid4(), original_query="q")
            final = await reasoning_agent._run_branches_and_select(
                initial, recursion_limit=50, branch_count=2
            )
        assert final.answer == strong.answer

    @pytest.mark.asyncio
    async def test_all_branches_fail_raises(self):
        async def fake_ainvoke(state, config=None):
            raise RuntimeError("boom")

        with patch.object(
            reasoning_agent._compiled_graph,
            "ainvoke",
            side_effect=fake_ainvoke,
        ):
            initial = AgentState(query_id=uuid.uuid4(), original_query="q")
            with pytest.raises(RuntimeError, match="boom"):
                await reasoning_agent._run_branches_and_select(
                    initial, recursion_limit=50, branch_count=2
                )

    @pytest.mark.asyncio
    async def test_branches_are_modality_orthogonal(self):
        """Each branch must differ on retrieval *modality* (not just a
        post-processing knob) — panel audit feedback. At N=3 we expect
        one hybrid, one graph-only, one vector-only."""
        seen: list[tuple[bool, bool]] = []
        winner = _state()

        async def fake_ainvoke(state, config=None):
            seen.append((state.graph_search_enabled, state.vector_search_enabled))
            return winner

        with patch.object(
            reasoning_agent._compiled_graph,
            "ainvoke",
            side_effect=fake_ainvoke,
        ):
            initial = AgentState(query_id=uuid.uuid4(), original_query="q")
            await reasoning_agent._run_branches_and_select(
                initial, recursion_limit=50, branch_count=3
            )
        # The set of (graph_on, vector_on) tuples must include all three
        # orthogonal recipes: (True,True), (True,False), (False,True).
        assert set(seen) == {(True, True), (True, False), (False, True)}


class TestRunReasoningAgentDispatch:
    @pytest.mark.asyncio
    async def test_branch_count_one_uses_single_path(self, monkeypatch):
        """Default (N=1) must NOT go through the fan-out path — that'd
        burn an extra coroutine wrapping for zero benefit."""
        from aim.config import get_settings

        s = get_settings()
        monkeypatch.setattr(s, "reasoning_branch_count", 1)

        single_called = {"n": 0}
        fan_out_called = {"n": 0}

        original_ainvoke = reasoning_agent._compiled_graph.ainvoke

        async def fake_ainvoke(state, config=None):
            single_called["n"] += 1
            return _state()

        async def fake_fan_out(*a, **kw):
            fan_out_called["n"] += 1
            return _state()

        with patch.object(
            reasoning_agent._compiled_graph, "ainvoke", side_effect=fake_ainvoke
        ), patch.object(
            reasoning_agent, "_run_branches_and_select", side_effect=fake_fan_out
        ):
            await reasoning_agent.run_reasoning_agent(
                query="q",
                query_id=uuid.uuid4(),
            )
        assert single_called["n"] == 1
        assert fan_out_called["n"] == 0

    @pytest.mark.asyncio
    async def test_branch_count_two_uses_fan_out(self, monkeypatch):
        from aim.config import get_settings

        s = get_settings()
        monkeypatch.setattr(s, "reasoning_branch_count", 2)

        fan_out_called = {"n": 0}

        async def fake_fan_out(initial, recursion_limit, branch_count):
            fan_out_called["n"] += 1
            assert branch_count == 2
            return _state()

        with patch.object(
            reasoning_agent, "_run_branches_and_select", side_effect=fake_fan_out
        ):
            await reasoning_agent.run_reasoning_agent(
                query="q",
                query_id=uuid.uuid4(),
            )
        assert fan_out_called["n"] == 1
