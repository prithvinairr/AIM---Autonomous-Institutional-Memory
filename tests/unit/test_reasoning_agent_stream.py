"""Tests for stream_reasoning_agent and _evaluate_route."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from aim.agents.reasoning_agent import _evaluate_route, _emit_token_metrics
from aim.agents.state import AgentState
from aim.schemas.query import CostInfo, ReasoningDepth


# ── _evaluate_route ─────────────────────────────────────────────────────────


class TestEvaluateRoute:
    def test_returns_reloop_when_needs_reloop(self):
        state = AgentState(
            query_id=uuid4(),
            original_query="test",
            needs_reloop=True,
        )
        assert _evaluate_route(state) == "reloop"

    def test_returns_done_when_no_reloop(self):
        state = AgentState(
            query_id=uuid4(),
            original_query="test",
            needs_reloop=False,
        )
        assert _evaluate_route(state) == "done"


# ── _emit_token_metrics ────────────────────────────────────────────────────


class TestEmitTokenMetrics:
    @patch("aim.config.get_settings")
    def test_emits_metrics_without_error(self, mock_settings):
        mock_settings.return_value = MagicMock(
            llm_input_cost_per_mtok=15.0,
            llm_output_cost_per_mtok=75.0,
            embedding_cost_per_mtok=0.02,
            embedding_model="text-embedding-3-small",
        )
        cost = CostInfo(
            input_tokens=100,
            output_tokens=50,
            embedding_tokens=200,
            estimated_cost_usd=0.01,
        )
        _emit_token_metrics("claude-opus-4-6", cost)


# ── stream_reasoning_agent ─────────────────────────────────────────────────


@dataclass
class FakeTokenChunk:
    content: str = ""
    is_final: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


def _mock_settings():
    return MagicMock(
        llm_temperature=0.3,
        llm_max_tokens=4096,
        llm_model="claude-opus-4-6",
        llm_input_cost_per_mtok=15.0,
        llm_output_cost_per_mtok=75.0,
        embedding_cost_per_mtok=0.02,
        embedding_model="text-embedding-3-small",
        node_timeout_seconds=20.0,
    )


class TestStreamReasoningAgent:
    @pytest.mark.asyncio
    async def test_yields_sub_query_and_token_and_done_chunks(self):
        """Full streaming flow: decompose → search → retrieve → synthesize → evaluate → done."""
        from aim.agents.reasoning_agent import stream_reasoning_agent
        from aim.schemas.provenance import ProvenanceMap, SourceReference, SourceType

        query_id = uuid4()

        # Build a realistic state that the nodes will "return"
        base_state = AgentState(
            query_id=query_id,
            original_query="What is auth?",
            reasoning_depth=ReasoningDepth.STANDARD,
            sub_queries=["How does auth work?"],
        )

        decomposed = base_state.model_copy(update={
            "sub_queries": ["How does auth work?"],
        })

        searched = decomposed.model_copy(update={
            "graph_entities": [],
            "graph_relationships": [],
            "sources": {
                "s1": SourceReference(
                    source_type=SourceType.NEO4J_GRAPH,
                    title="Auth",
                    confidence=0.9,
                    content_snippet="auth data",
                ),
            },
            "sub_query_source_map": {"How does auth work?": ["s1"]},
            "reasoning_steps": ["Graph search done"],
        })

        mcp_fetched = decomposed.model_copy(update={
            "mcp_context": [],
            "sources": {},
            "sub_query_source_map": {},
            "reasoning_steps": ["MCP: skipped"],
        })

        vector_retrieved = searched.model_copy(update={
            "sources": {
                **searched.sources,
                "v1": SourceReference(
                    source_type=SourceType.PINECONE_VECTOR,
                    title="Auth vector",
                    confidence=0.8,
                    content_snippet="vector match",
                ),
            },
        })

        evaluated = vector_retrieved.model_copy(update={
            "answer": "Auth uses JWT tokens. [SRC:s1]",
            "needs_reloop": False,
            "evaluation_score": 0.85,
        })

        # Mock all node functions
        mock_decompose = AsyncMock(return_value=decomposed)
        mock_search = AsyncMock(return_value=searched)
        mock_mcp = AsyncMock(return_value=mcp_fetched)
        mock_vectors = AsyncMock(return_value=vector_retrieved)
        mock_evaluate = AsyncMock(return_value=evaluated)

        # Mock LLM stream
        async def fake_stream(*args, **kwargs):
            yield FakeTokenChunk(content="Auth uses ")
            yield FakeTokenChunk(content="JWT tokens.")
            yield FakeTokenChunk(content="", is_final=True, input_tokens=100, output_tokens=50)

        mock_llm = MagicMock()
        mock_llm.stream = fake_stream

        with (
            patch("aim.agents.reasoning_agent._decompose_fn", mock_decompose),
            patch("aim.agents.reasoning_agent._search_graph_fn", mock_search),
            patch("aim.agents.reasoning_agent._fetch_mcp_fn", mock_mcp),
            patch("aim.agents.reasoning_agent._retrieve_vectors_fn", mock_vectors),
            patch("aim.agents.reasoning_agent._evaluate_fn", mock_evaluate),
            patch("aim.llm.get_llm_provider", return_value=mock_llm),
            patch("aim.config.get_settings", return_value=_mock_settings()),
            patch("aim.agents.nodes.synthesizer._build_messages", return_value=[]),
            patch("aim.agents.reasoning_agent._build_context_block", return_value="ctx"),
        ):
            chunks = []
            async for chunk in stream_reasoning_agent(
                query="What is auth?",
                query_id=query_id,
                reasoning_depth=ReasoningDepth.STANDARD,
            ):
                chunks.append(chunk)

        # Verify chunk types
        types = [c.chunk_type for c in chunks]
        assert "sub_query" in types
        assert "token" in types
        assert "done" in types

        # Done chunk has sources and cost
        done_chunk = [c for c in chunks if c.chunk_type == "done"][0]
        assert done_chunk.cost_info is not None
        assert done_chunk.confidence is not None

    @pytest.mark.asyncio
    async def test_stream_with_conversation_history(self):
        """Streaming with history records conversation turns metric."""
        from aim.agents.reasoning_agent import stream_reasoning_agent
        from aim.schemas.provenance import SourceReference, SourceType

        query_id = uuid4()

        base = AgentState(
            query_id=query_id,
            original_query="follow up",
            sub_queries=["follow up query"],
        )

        decomposed = base.model_copy(update={"sub_queries": ["follow up query"]})
        searched = decomposed.model_copy(update={
            "sources": {},
            "sub_query_source_map": {},
            "reasoning_steps": [],
        })
        mcp_fetched = decomposed.model_copy(update={
            "mcp_context": [],
            "sources": {},
            "sub_query_source_map": {},
            "reasoning_steps": [],
        })
        vector_ret = searched
        evaluated = vector_ret.model_copy(update={
            "answer": "answer",
            "needs_reloop": False,
            "evaluation_score": 0.9,
        })

        async def fake_stream(*a, **kw):
            yield FakeTokenChunk(content="answer")
            yield FakeTokenChunk(is_final=True, input_tokens=10, output_tokens=5)

        mock_llm = MagicMock()
        mock_llm.stream = fake_stream

        history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]

        with (
            patch("aim.agents.reasoning_agent._decompose_fn", AsyncMock(return_value=decomposed)),
            patch("aim.agents.reasoning_agent._search_graph_fn", AsyncMock(return_value=searched)),
            patch("aim.agents.reasoning_agent._fetch_mcp_fn", AsyncMock(return_value=mcp_fetched)),
            patch("aim.agents.reasoning_agent._retrieve_vectors_fn", AsyncMock(return_value=vector_ret)),
            patch("aim.agents.reasoning_agent._evaluate_fn", AsyncMock(return_value=evaluated)),
            patch("aim.llm.get_llm_provider", return_value=mock_llm),
            patch("aim.config.get_settings", return_value=_mock_settings()),
            patch("aim.agents.nodes.synthesizer._build_messages", return_value=[]),
            patch("aim.agents.reasoning_agent._build_context_block", return_value="ctx"),
        ):
            chunks = []
            async for chunk in stream_reasoning_agent(
                query="follow up",
                query_id=query_id,
                conversation_history=history,
            ):
                chunks.append(chunk)

        assert any(c.chunk_type == "done" for c in chunks)

    @pytest.mark.asyncio
    async def test_stream_reloop_yields_re_searching_message(self):
        """When evaluator triggers reloop, stream emits re-searching message."""
        from aim.agents.reasoning_agent import stream_reasoning_agent
        from aim.schemas.provenance import SourceReference, SourceType

        query_id = uuid4()

        base = AgentState(
            query_id=query_id,
            original_query="test",
            sub_queries=["sq1"],
        )
        decomposed = base.model_copy(update={"sub_queries": ["sq1"]})
        searched = decomposed.model_copy(update={
            "sources": {},
            "sub_query_source_map": {},
            "reasoning_steps": [],
        })
        mcp_fetched = decomposed.model_copy(update={
            "mcp_context": [],
            "sources": {},
            "sub_query_source_map": {},
            "reasoning_steps": [],
        })

        # First eval: reloop. Second eval: done.
        call_count = 0

        async def fake_evaluate(state):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return state.model_copy(update={
                    "needs_reloop": True,
                    "evaluation_score": 0.3,
                    "loop_count": 1,
                })
            return state.model_copy(update={
                "needs_reloop": False,
                "evaluation_score": 0.8,
            })

        async def fake_stream(*a, **kw):
            yield FakeTokenChunk(content="answer")
            yield FakeTokenChunk(is_final=True, input_tokens=10, output_tokens=5)

        mock_llm = MagicMock()
        mock_llm.stream = fake_stream

        with (
            patch("aim.agents.reasoning_agent._decompose_fn", AsyncMock(return_value=decomposed)),
            patch("aim.agents.reasoning_agent._search_graph_fn", AsyncMock(return_value=searched)),
            patch("aim.agents.reasoning_agent._fetch_mcp_fn", AsyncMock(return_value=mcp_fetched)),
            patch("aim.agents.reasoning_agent._retrieve_vectors_fn", AsyncMock(return_value=searched)),
            patch("aim.agents.reasoning_agent._evaluate_fn", AsyncMock(side_effect=fake_evaluate)),
            patch("aim.llm.get_llm_provider", return_value=mock_llm),
            patch("aim.config.get_settings", return_value=_mock_settings()),
            patch("aim.agents.nodes.synthesizer._build_messages", return_value=[]),
            patch("aim.agents.reasoning_agent._build_context_block", return_value="ctx"),
        ):
            chunks = []
            async for chunk in stream_reasoning_agent(
                query="test",
                query_id=query_id,
            ):
                chunks.append(chunk)

        # Should have a re-searching sub_query chunk
        sub_queries = [c for c in chunks if c.chunk_type == "sub_query"]
        assert any("re-searching" in (c.content or "").lower() for c in sub_queries)
        # Should still end with done
        assert chunks[-1].chunk_type == "done"
