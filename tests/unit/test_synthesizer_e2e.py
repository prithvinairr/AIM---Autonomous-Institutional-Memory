"""Unit tests for synthesize_answer — the full synthesizer node.

Mocks the LLM provider to return a known answer, then verifies
provenance map construction, citation extraction, confidence scoring,
and token tracking.
"""
from __future__ import annotations

from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.agents.state import AgentState
from aim.agents.nodes.synthesizer import synthesize_answer, _build_context_block, _build_messages
from aim.llm.base import LLMResponse
from aim.schemas.graph import GraphEntity
from aim.schemas.provenance import SourceReference, SourceType
from aim.schemas.query import ReasoningDepth


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_state(**overrides) -> AgentState:
    neo_src = SourceReference(
        source_type=SourceType.NEO4J_GRAPH,
        uri="neo4j://node/1",
        title="Auth Service",
        content_snippet="Auth service owned by platform",
        confidence=0.95,
        metadata={"entity_id": "1", "labels": ["Service"]},
    )
    vec_src = SourceReference(
        source_type=SourceType.PINECONE_VECTOR,
        uri="https://docs.example.com/auth",
        title="Auth Docs",
        content_snippet="Auth documentation page",
        confidence=0.82,
        metadata={"vector_id": "v1"},
    )
    entities = [
        GraphEntity(entity_id="1", labels=["Service"], properties={"name": "Auth"}, score=0.95),
    ]
    defaults = dict(
        query_id=uuid4(),
        original_query="Who owns the auth service?",
        sub_queries=["Who owns auth?", "Auth recent changes?"],
        graph_entities=entities,
        sources={neo_src.source_id: neo_src, vec_src.source_id: vec_src},
        sub_query_source_map={
            "Who owns auth?": [neo_src.source_id],
            "Auth recent changes?": [vec_src.source_id],
        },
        vector_snippets=[{"id": "v1", "text": "auth docs text", "score": 0.82}],
        input_tokens=100,
        output_tokens=50,
    )
    defaults.update(overrides)
    return AgentState(**defaults)


def _mock_settings():
    s = MagicMock()
    s.llm_model = "claude-opus-4-6"
    s.llm_temperature = 0.1
    s.llm_max_tokens = 4096
    s.anthropic_api_key = "sk-test"
    s.llm_provider = "anthropic"
    s.llm_base_url = ""
    return s


def _mock_llm_provider(answer: str, input_tokens: int = 800, output_tokens: int = 300):
    """Create a mock LLM provider returning a fixed response."""
    provider = AsyncMock()
    provider.invoke = AsyncMock(return_value=LLMResponse(
        content=answer,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model="test",
    ))
    return provider


# ── synthesize_answer ────────────────────────────────────────────────────────

async def test_synthesize_produces_provenance_map():
    state = _make_state()
    src_ids = list(state.sources.keys())
    answer = f"The auth service is owned by platform team. [SRC:{src_ids[0]}]"

    mock_provider = _mock_llm_provider(answer)

    with patch("aim.agents.nodes.synthesizer.get_settings", return_value=_mock_settings()), \
         patch("aim.agents.nodes.synthesizer.get_llm_provider", return_value=mock_provider):
        result = await synthesize_answer(state)

    assert result.provenance is not None
    assert result.provenance.overall_confidence > 0
    assert len(result.provenance.sources) == 2
    assert len(result.provenance.sub_query_traces) == 2
    assert result.answer == answer


async def test_synthesize_accumulates_tokens():
    state = _make_state(input_tokens=100, output_tokens=50)
    answer = "Simple answer"

    mock_provider = _mock_llm_provider(answer, input_tokens=800, output_tokens=300)

    with patch("aim.agents.nodes.synthesizer.get_settings", return_value=_mock_settings()), \
         patch("aim.agents.nodes.synthesizer.get_llm_provider", return_value=mock_provider):
        result = await synthesize_answer(state)

    assert result.input_tokens == 900   # 100 + 800
    assert result.output_tokens == 350  # 50 + 300


async def test_synthesize_handles_no_citations():
    state = _make_state()
    answer = "I don't have enough information to answer."

    mock_provider = _mock_llm_provider(answer)

    with patch("aim.agents.nodes.synthesizer.get_settings", return_value=_mock_settings()), \
         patch("aim.agents.nodes.synthesizer.get_llm_provider", return_value=mock_provider):
        result = await synthesize_answer(state)

    assert result.provenance is not None
    # Confidence should be lower since nothing was cited
    assert len(result.citation_map) == 0


async def test_synthesize_with_conversation_history():
    history = [
        {"role": "user", "content": "What is auth?"},
        {"role": "assistant", "content": "Auth is the authentication service."},
    ]
    state = _make_state(conversation_history=history)
    answer = "As mentioned, auth is owned by platform."

    mock_provider = _mock_llm_provider(answer)

    with patch("aim.agents.nodes.synthesizer.get_settings", return_value=_mock_settings()), \
         patch("aim.agents.nodes.synthesizer.get_llm_provider", return_value=mock_provider):
        result = await synthesize_answer(state)

    assert result.answer == answer


async def test_synthesize_raises_on_llm_error():
    state = _make_state()

    mock_provider = AsyncMock()
    mock_provider.invoke = AsyncMock(side_effect=RuntimeError("LLM down"))

    with patch("aim.agents.nodes.synthesizer.get_settings", return_value=_mock_settings()), \
         patch("aim.agents.nodes.synthesizer.get_llm_provider", return_value=mock_provider):
        with pytest.raises(RuntimeError, match="LLM down"):
            await synthesize_answer(state)


# ── _build_context_block ─────────────────────────────────────────────────────

async def test_build_context_block_includes_all_sections():
    from aim.schemas.mcp import MCPContext, SlackContext, SlackMessage
    msg = SlackMessage(
        message_id="m1", channel="general", author="user1",
        text="slack msg", timestamp="2026-01-01T00:00:00Z",
    )
    mcp = MCPContext(slack_contexts=[SlackContext(channel="general", messages=[msg], query_relevance_score=0.8)])
    state = _make_state(mcp_context=mcp)

    block = await _build_context_block(state)
    # Under graph_aware default (δ.2), the entity block is titled
    # "Nodes (typed subgraph)"; the flat "Knowledge Graph Entities" header
    # only appears when operators opt back to flat via SYNTHESIS_MODE=flat.
    assert "Nodes (typed subgraph)" in block
    assert "Document Snippets" in block
    assert "Live Context" in block
    assert "Source ID Reference" in block


async def test_build_context_block_empty_state():
    state = AgentState(query_id=uuid4(), original_query="test")
    block = await _build_context_block(state)
    # No sections should appear for empty state
    assert "Knowledge Graph" not in block


# ── _build_messages ──────────────────────────────────────────────────────────

def test_build_messages_without_history():
    state = AgentState(
        query_id=uuid4(),
        original_query="test query",
        sub_queries=["sub1"],
    )
    msgs = _build_messages(state, "context block")
    # System + 1 user message
    assert len(msgs) == 2
    assert "test query" in msgs[1]["content"]


def test_build_messages_with_history():
    state = AgentState(
        query_id=uuid4(),
        original_query="follow-up",
        sub_queries=["sub1"],
        conversation_history=[
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "first answer"},
        ],
    )
    msgs = _build_messages(state, "context")
    # System + 2 history messages + 1 current = 4
    assert len(msgs) == 4


# ── Relationship path (BFS) ─────────────────────────────────────────────────

async def test_synthesize_populates_relationship_paths():
    """Graph provenance nodes should have relationship_path populated via BFS."""
    from aim.schemas.graph import GraphRelationship

    neo_src1 = SourceReference(
        source_type=SourceType.NEO4J_GRAPH,
        uri="neo4j://node/root",
        title="Auth Service",
        content_snippet="Root entity",
        confidence=0.95,
        metadata={"entity_id": "root", "labels": ["Service"]},
    )
    neo_src2 = SourceReference(
        source_type=SourceType.NEO4J_GRAPH,
        uri="neo4j://node/neighbour",
        title="Alex Rivera",
        content_snippet="Neighbour entity",
        confidence=0.85,
        metadata={"entity_id": "neighbour", "labels": ["Person"]},
    )
    # BFS roots = first 5 entities, so pad with dummies so "neighbour" is 6th
    root_entities = [
        GraphEntity(entity_id="root", labels=["Service"], properties={"name": "Auth"}, score=0.95),
    ]
    filler = [
        GraphEntity(entity_id=f"filler{i}", labels=["Thing"], properties={"name": f"F{i}"}, score=0.5)
        for i in range(4)
    ]
    neighbour = GraphEntity(entity_id="neighbour", labels=["Person"], properties={"name": "Alex"}, score=0.85)
    entities = root_entities + filler + [neighbour]

    rels = [
        GraphRelationship(
            rel_id="r1",
            rel_type="OWNS",
            source_id="neighbour",
            target_id="root",
        ),
    ]

    state = AgentState(
        query_id=uuid4(),
        original_query="Who owns auth?",
        sub_queries=["Who owns auth?"],
        graph_entities=entities,
        graph_relationships=rels,
        sources={neo_src1.source_id: neo_src1, neo_src2.source_id: neo_src2},
        sub_query_source_map={"Who owns auth?": [neo_src1.source_id, neo_src2.source_id]},
    )

    answer = "Alex owns the auth service."
    mock_provider = _mock_llm_provider(answer)

    with patch("aim.agents.nodes.synthesizer.get_settings", return_value=_mock_settings()), \
         patch("aim.agents.nodes.synthesizer.get_llm_provider", return_value=mock_provider):
        result = await synthesize_answer(state)

    assert result.provenance is not None
    # At least one graph node should have a non-empty relationship_path
    paths = [n.relationship_path for n in result.provenance.graph_nodes]
    # Root node has empty path, neighbour has ["OWNS"]
    assert any(len(p) > 0 for p in paths)


async def test_synthesize_relationship_paths_empty_when_no_rels():
    """With no relationships, all paths should be empty."""
    state = _make_state()
    answer = "Test answer"
    mock_provider = _mock_llm_provider(answer)

    with patch("aim.agents.nodes.synthesizer.get_settings", return_value=_mock_settings()), \
         patch("aim.agents.nodes.synthesizer.get_llm_provider", return_value=mock_provider):
        result = await synthesize_answer(state)

    for node in result.provenance.graph_nodes:
        assert node.relationship_path == []
