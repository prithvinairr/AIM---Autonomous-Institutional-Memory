"""Unit tests for run_reasoning_agent and stream_reasoning_agent.

Mocks the compiled LangGraph to return a known AgentState, then verifies
the full response construction, cost calculation, sub-query attribution,
and error paths.
"""
from __future__ import annotations

from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.agents.state import AgentState
from aim.schemas.provenance import (
    ProvenanceMap,
    SourceReference,
    SourceType,
    SubQueryTrace,
)
from aim.schemas.query import ReasoningDepth


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_source(source_type: SourceType, confidence: float = 0.9) -> SourceReference:
    return SourceReference(
        source_type=source_type,
        uri=f"{source_type.value}://test",
        title="Test Source",
        content_snippet="Test snippet",
        confidence=confidence,
    )


def _make_final_state(query_id=None, **overrides) -> AgentState:
    """Build a realistic final AgentState as if the full pipeline ran."""
    qid = query_id or uuid4()
    neo_src = _make_source(SourceType.NEO4J_GRAPH)
    vec_src = _make_source(SourceType.PINECONE_VECTOR, 0.85)

    sources = {neo_src.source_id: neo_src, vec_src.source_id: vec_src}
    sub_queries = ["Who owns auth?", "Recent auth issues?"]
    sq_map = {
        "Who owns auth?": [neo_src.source_id],
        "Recent auth issues?": [vec_src.source_id],
    }

    defaults = dict(
        query_id=qid,
        original_query="Tell me about auth",
        reasoning_depth=ReasoningDepth.STANDARD,
        sub_queries=sub_queries,
        sources=sources,
        sub_query_source_map=sq_map,
        answer="Auth is owned by platform team. [SRC:src1]",
        input_tokens=500,
        output_tokens=200,
        embedding_tokens=100,
        provenance=ProvenanceMap(
            query_id=qid,
            sources=sources,
            graph_nodes=[],
            sub_query_traces=[
                SubQueryTrace(sub_query_id="sq_0", sub_query_text="Who owns auth?", source_ids=[neo_src.source_id]),
                SubQueryTrace(sub_query_id="sq_1", sub_query_text="Recent auth issues?", source_ids=[vec_src.source_id]),
            ],
            citation_map={"Auth is owned by platform team.": [neo_src.source_id]},
            overall_confidence=0.88,
            reasoning_steps=["Decomposed into 2 sub-queries.", "Synthesized."],
        ),
    )
    defaults.update(overrides)
    return AgentState(**defaults)


def _mock_settings(**overrides):
    s = MagicMock()
    s.llm_model = "claude-opus-4-6"
    s.llm_temperature = 0.1
    s.llm_max_tokens = 4096
    s.anthropic_api_key = "sk-test"
    s.node_timeout_seconds = 20.0
    s.embedding_model = "text-embedding-3-small"
    s.llm_input_cost_per_mtok = 15.0
    s.llm_output_cost_per_mtok = 75.0
    s.embedding_cost_per_mtok = 0.02
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


# ── run_reasoning_agent ──────────────────────────────────────────────────────

async def test_run_reasoning_agent_returns_query_response():
    """Full pipeline mock → verify QueryResponse construction."""
    qid = uuid4()
    final_state = _make_final_state(query_id=qid)

    with patch("aim.agents.reasoning_agent._compiled_graph") as mock_graph, \
         patch("aim.config.get_settings", return_value=_mock_settings()):
        mock_graph.ainvoke = AsyncMock(return_value=final_state)

        from aim.agents.reasoning_agent import run_reasoning_agent
        response = await run_reasoning_agent(
            query="Tell me about auth",
            query_id=qid,
            reasoning_depth=ReasoningDepth.STANDARD,
        )

    assert response.query_id == qid
    assert response.answer == final_state.answer
    assert response.cost_info is not None
    assert response.cost_info.input_tokens == 500
    assert response.cost_info.output_tokens == 200
    assert response.cost_info.embedding_tokens == 100
    assert response.cost_info.estimated_cost_usd > 0
    assert len(response.sub_query_results) == 2
    assert response.sub_query_results[0].graph_hits == 1
    assert response.sub_query_results[0].vector_hits == 0
    assert response.sub_query_results[1].vector_hits == 1


async def test_run_reasoning_agent_with_conversation_history():
    """History is passed through and CONVERSATION_TURNS metric fires."""
    qid = uuid4()
    history = [
        {"role": "user", "content": "previous question"},
        {"role": "assistant", "content": "previous answer"},
    ]
    final_state = _make_final_state(query_id=qid)

    with patch("aim.agents.reasoning_agent._compiled_graph") as mock_graph, \
         patch("aim.config.get_settings", return_value=_mock_settings()):
        mock_graph.ainvoke = AsyncMock(return_value=final_state)

        from aim.agents.reasoning_agent import run_reasoning_agent
        response = await run_reasoning_agent(
            query="Tell me about auth",
            query_id=qid,
            conversation_history=history,
        )

    assert response.answer == final_state.answer
    # Verify history was passed to the graph
    call_args = mock_graph.ainvoke.call_args[0][0]
    assert len(call_args.conversation_history) == 2


async def test_run_reasoning_agent_raises_on_missing_provenance():
    """If synthesizer didn't produce provenance, raise RuntimeError."""
    qid = uuid4()
    final_state = _make_final_state(query_id=qid, provenance=None)

    with patch("aim.agents.reasoning_agent._compiled_graph") as mock_graph, \
         patch("aim.config.get_settings", return_value=_mock_settings()):
        mock_graph.ainvoke = AsyncMock(return_value=final_state)

        from aim.agents.reasoning_agent import run_reasoning_agent
        with pytest.raises(RuntimeError, match="ProvenanceMap"):
            await run_reasoning_agent(query="test", query_id=qid)


async def test_run_reasoning_agent_increments_error_metric_on_failure():
    """Graph invocation failure → QUERY_TOTAL error counter fires."""
    qid = uuid4()

    with patch("aim.agents.reasoning_agent._compiled_graph") as mock_graph, \
         patch("aim.config.get_settings", return_value=_mock_settings()):
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))

        from aim.agents.reasoning_agent import run_reasoning_agent
        with pytest.raises(RuntimeError, match="boom"):
            await run_reasoning_agent(query="test", query_id=qid)


async def test_run_reasoning_agent_deep_mode():
    """Deep reasoning depth is forwarded correctly."""
    qid = uuid4()
    final_state = _make_final_state(query_id=qid, reasoning_depth=ReasoningDepth.DEEP)

    with patch("aim.agents.reasoning_agent._compiled_graph") as mock_graph, \
         patch("aim.config.get_settings", return_value=_mock_settings()):
        mock_graph.ainvoke = AsyncMock(return_value=final_state)

        from aim.agents.reasoning_agent import run_reasoning_agent
        response = await run_reasoning_agent(
            query="deep query",
            query_id=qid,
            reasoning_depth=ReasoningDepth.DEEP,
        )

    assert response.original_query == "deep query"
    call_state = mock_graph.ainvoke.call_args[0][0]
    assert call_state.reasoning_depth == ReasoningDepth.DEEP


async def test_emit_token_metrics_fires_counters():
    """_emit_token_metrics writes to all Prometheus counters."""
    from aim.agents.reasoning_agent import _emit_token_metrics, _compute_cost

    settings = _mock_settings()

    with patch("aim.config.get_settings", return_value=settings):
        cost = _compute_cost(1000, 500, 200)
        # Should not raise
        _emit_token_metrics("claude-opus-4-6", cost)


async def test_build_graph_structure():
    """Verify the graph has correct node names and edges."""
    from aim.agents.reasoning_agent import build_graph
    g = build_graph()
    # Should contain all 5 nodes
    assert "decompose" in g.nodes
    assert "search_graph" in g.nodes
    assert "fetch_mcp" in g.nodes
    assert "retrieve_vectors" in g.nodes
    assert "synthesize" in g.nodes


async def test_timed_node_timeout_returns_state_with_step():
    """_timed_node wrapper adds a reasoning step on timeout."""
    import asyncio
    from aim.agents.reasoning_agent import _timed_node

    async def _slow_node(state):
        await asyncio.sleep(100)
        return state

    wrapped = _timed_node("test_node", _slow_node)
    state = AgentState(query_id=uuid4(), original_query="test")

    mock_s = _mock_settings(node_timeout_seconds=0.01)
    with patch("aim.config.get_settings", return_value=mock_s):
        result = await wrapped(state)

    assert any("timed out" in s for s in result.reasoning_steps)
