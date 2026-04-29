"""Unit tests for the graph searcher node."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from aim.agents.nodes.graph_searcher import (
    _merge_teacher_bfs_candidates,
    search_knowledge_graph,
)
from aim.agents.state import AgentState
from aim.schemas.graph import GraphEntity, GraphSearchResult
from aim.schemas.query import ReasoningDepth

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> AgentState:
    defaults = {
        "query_id": uuid4(),
        "original_query": "test query",
        "reasoning_depth": ReasoningDepth.STANDARD,
        "sub_queries": ["What is X?", "Who owns Y?"],
    }
    defaults.update(overrides)
    return AgentState(**defaults)


def _make_entity(entity_id: str = "e1", labels: list[str] | None = None, score: float = 0.9):
    return GraphEntity(
        entity_id=entity_id,
        labels=labels or ["Entity"],
        properties={"name": f"Entity {entity_id}"},
        score=score,
    )


def _make_search_result(entities=None, relationships=None):
    return GraphSearchResult(
        entities=entities or [],
        relationships=relationships or [],
        total_traversed=len(entities or []) + len(relationships or []),
    )


def _mock_settings(**overrides):
    defaults = {
        "graph_search_depth": 2,
        "node_timeout_seconds": 20.0,
        "graph_use_hybrid_search": False,
        "graph_proactive_paths": False,
        "graph_teacher_bfs_enabled": True,
        "graph_teacher_bfs_limit": 20,
        "graph_hub_degree_limit": 25,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


# ── Tests ────────────────────────────────────────────────────────────────────


def test_teacher_bfs_merge_boosts_existing_and_appends_new_sources():
    existing = [_make_entity("a", score=0.5), _make_entity("b", score=0.4)]
    teacher = [_make_entity("b", score=1.2), _make_entity("c", score=1.1)]
    sources = {}
    seen = {"a", "b"}

    merged = _merge_teacher_bfs_candidates(existing, sources, seen, teacher)

    assert [e.entity_id for e in merged[:3]] == ["b", "c", "a"]
    assert merged[0].score == pytest.approx(1.6)
    assert "c" in seen
    assert len(sources) == 1
    ref = next(iter(sources.values()))
    assert ref.metadata["entity_id"] == "c"
    assert ref.metadata["teacher_bfs"] is True


@pytest.mark.asyncio
async def test_returns_unchanged_state_when_no_sub_queries():
    state = _make_state(sub_queries=[])
    result = await search_knowledge_graph(state)
    assert result.graph_entities == []
    assert result.graph_relationships == []


@pytest.mark.asyncio
async def test_searches_all_sub_queries_in_standard_mode():
    entities = [_make_entity("e1"), _make_entity("e2")]
    mock_result = _make_search_result(entities=entities)

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=mock_result)
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(return_value=mock_result)

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state()
                result = await search_knowledge_graph(state)

    # Both sub-queries should be searched (gather called)
    assert mock_breaker.call.call_count == 2
    assert len(result.graph_entities) > 0


@pytest.mark.asyncio
async def test_shallow_mode_limits_to_first_sub_query():
    mock_result = _make_search_result(entities=[_make_entity("e1")])

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=mock_result)
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(return_value=mock_result)

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(
                    reasoning_depth=ReasoningDepth.SHALLOW,
                    sub_queries=["Q1", "Q2", "Q3"],
                )
                await search_knowledge_graph(state)

    # SHALLOW: only first sub-query searched
    assert mock_breaker.call.call_count == 1


@pytest.mark.asyncio
async def test_deep_mode_caps_search_depth_at_5():
    mock_result = _make_search_result(entities=[])

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=mock_result)
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(return_value=mock_result)

    with patch(
        "aim.agents.nodes.graph_searcher.get_settings",
        return_value=_mock_settings(graph_search_depth=4),
    ):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(reasoning_depth=ReasoningDepth.DEEP, sub_queries=["Q"])
                await search_knowledge_graph(state)

    # depth = min(4*2, 5) = 5
    call_kwargs = mock_breaker.call.call_args
    assert call_kwargs.kwargs["max_depth"] == 5


@pytest.mark.asyncio
async def test_deduplicates_entities_across_sub_queries():
    # Same entity returned for both sub-queries
    shared_entity = _make_entity("shared")
    mock_result = _make_search_result(entities=[shared_entity])

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(return_value=mock_result)

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(sub_queries=["Q1", "Q2"])
                result = await search_knowledge_graph(state)

    # Entity appears only once despite being in both search results
    assert len(result.graph_entities) == 1


@pytest.mark.asyncio
async def test_tracks_source_attribution_per_sub_query():
    e1 = _make_entity("e1")
    e2 = _make_entity("e2")

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(
        side_effect=[
            _make_search_result(entities=[e1]),
            _make_search_result(entities=[e2]),
        ]
    )

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(sub_queries=["Q1", "Q2"])
                result = await search_knowledge_graph(state)

    # Each sub-query should have its own source IDs
    assert "Q1" in result.sub_query_source_map
    assert "Q2" in result.sub_query_source_map
    assert result.sub_query_source_map["Q1"] != result.sub_query_source_map["Q2"]


@pytest.mark.asyncio
async def test_exact_identifier_anchor_prepends_incident_context():
    broad_entity = _make_entity("runbook", labels=["Document"], score=5.0)
    broad_entity = broad_entity.model_copy(
        update={"properties": {"name": "Incident Response Playbook"}}
    )
    incident = _make_entity("inc-099", labels=["Incident"], score=3.0)
    incident = incident.model_copy(update={"properties": {"name": "INC-2025-099"}})

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(
        side_effect=[
            _make_search_result(entities=[broad_entity]),
            _make_search_result(entities=[incident]),
        ]
    )

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(
                    original_query="Who is leading the response to INC-2025-099?",
                    sub_queries=["Who is leading the response to INC-2025-099?"],
                )
                result = await search_knowledge_graph(state)

    assert result.graph_entities[0].entity_id == "inc-099"
    assert any(entity.entity_id == broad_entity.entity_id for entity in result.graph_entities)
    assert "Who is leading the response to INC-2025-099?" in result.sub_query_source_map
    assert "INC-2025-099" in result.sub_query_source_map
    assert any("exact identifier anchoring" in step.lower() for step in result.reasoning_steps)


@pytest.mark.asyncio
async def test_circuit_open_adds_reasoning_step():
    from aim.utils.circuit_breaker import CircuitOpenError

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(side_effect=CircuitOpenError("neo4j"))

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(sub_queries=["Q1"])
                result = await search_knowledge_graph(state)

    assert any("circuit open" in step for step in result.reasoning_steps)


@pytest.mark.asyncio
async def test_creates_source_references_with_neo4j_type():
    entity = _make_entity("e1", labels=["Person"], score=0.85)
    mock_result = _make_search_result(entities=[entity])

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(return_value=mock_result)

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(sub_queries=["Q1"])
                result = await search_knowledge_graph(state)

    assert len(result.sources) == 1
    src = next(iter(result.sources.values()))
    assert src.source_type.value == "neo4j_graph"
    assert src.confidence == 0.85
    assert "neo4j://node/e1" == src.uri


@pytest.mark.asyncio
async def test_deep_mode_iterative_refinement_on_sparse_results():
    """DEEP mode triggers iterative refinement when initial results are sparse."""
    # First search returns nothing, second (refinement) returns results
    empty_result = _make_search_result(entities=[])
    refined_entity = _make_entity("refined_e1", labels=["Service"], score=0.75)
    refined_result = _make_search_result(entities=[refined_entity])

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    # First call returns empty (sparse), refinement returns entity
    mock_breaker.call = AsyncMock(side_effect=[empty_result, refined_result])

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(
                    reasoning_depth=ReasoningDepth.DEEP,
                    sub_queries=["sparse query"],
                    retries=0,
                )
                result = await search_knowledge_graph(state)

    # Iterative refinement should have been triggered
    assert any("refinement" in step.lower() for step in result.reasoning_steps)
    assert len(result.graph_entities) == 1
    assert result.graph_entities[0].entity_id == "refined_e1"
    assert result.retries == 1


@pytest.mark.asyncio
async def test_deep_mode_no_refinement_when_results_sufficient():
    """DEEP mode skips refinement when enough entities are found."""
    entities = [_make_entity(f"e{i}") for i in range(5)]
    mock_result = _make_search_result(entities=entities)

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(return_value=mock_result)

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(
                    reasoning_depth=ReasoningDepth.DEEP,
                    sub_queries=["Q1"],
                    retries=0,
                )
                result = await search_knowledge_graph(state)

    # No refinement — enough entities found
    assert not any("refinement" in step.lower() for step in result.reasoning_steps)


@pytest.mark.asyncio
async def test_deep_mode_no_refinement_on_retry():
    """DEEP mode doesn't refine twice (retries >= 1)."""
    empty_result = _make_search_result(entities=[])

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(return_value=empty_result)

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(
                    reasoning_depth=ReasoningDepth.DEEP,
                    sub_queries=["Q1"],
                    retries=1,  # already retried
                )
                result = await search_knowledge_graph(state)

    # No refinement — already retried once
    assert not any("refinement" in step.lower() for step in result.reasoning_steps)


@pytest.mark.asyncio
async def test_timeout_adds_reasoning_step():
    """A timeout on a sub-query adds a reasoning step and continues."""
    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(side_effect=TimeoutError())

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(sub_queries=["Q1"])
                result = await search_knowledge_graph(state)

    assert any("timed out" in step for step in result.reasoning_steps)


@pytest.mark.asyncio
async def test_general_exception_in_search_is_nonfatal():
    """An unexpected exception in the main search loop adds a reasoning step but doesn't crash."""
    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(side_effect=RuntimeError("unexpected DB error"))

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(sub_queries=["Q1"])
                result = await search_knowledge_graph(state)

    assert any("failed" in step.lower() for step in result.reasoning_steps)


@pytest.mark.asyncio
async def test_path_finding_with_entity_pairs():
    """When entity_pairs are set, path-finding is triggered."""
    mock_result = _make_search_result(entities=[_make_entity("e1")])
    path_data = [{"path_rels": [{"rel_type": "OWNS"}], "hops": 1}]

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    # breaker.call returns search result first, then path data
    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(side_effect=[mock_result, path_data])

    mock_path_client = MagicMock()
    mock_path_client.lookup_entity_name = AsyncMock(side_effect=["aim-id-a", "aim-id-b"])
    mock_path_client.close = AsyncMock()

    # Neo4jClient is called twice: once for main search, once for path-finding
    client_instances = [mock_client, mock_path_client]
    call_count = {"n": 0}

    def neo4j_factory():
        idx = min(call_count["n"], len(client_instances) - 1)
        call_count["n"] += 1
        return client_instances[idx]

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", side_effect=neo4j_factory):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(
                    sub_queries=["Q1"],
                    entity_pairs=[["Service A", "Service B"]],
                )
                result = await search_knowledge_graph(state)

    assert len(result.path_results) >= 1
    assert any("path found" in step.lower() for step in result.reasoning_steps)


@pytest.mark.asyncio
async def test_path_finding_timeout_adds_step():
    """Path-finding timeout doesn't crash, adds a reasoning step."""
    mock_result = _make_search_result(entities=[_make_entity("e1")])

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(return_value=mock_result)

    mock_path_client = MagicMock()
    mock_path_client.lookup_entity_name = AsyncMock(side_effect=TimeoutError())
    mock_path_client.close = AsyncMock()

    client_instances = [mock_client, mock_path_client]
    call_count = {"n": 0}

    def neo4j_factory():
        idx = min(call_count["n"], len(client_instances) - 1)
        call_count["n"] += 1
        return client_instances[idx]

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", side_effect=neo4j_factory):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(
                    sub_queries=["Q1"],
                    entity_pairs=[["A", "B"]],
                )
                result = await search_knowledge_graph(state)

    assert any("timed out" in step.lower() for step in result.reasoning_steps)


@pytest.mark.asyncio
async def test_path_finding_skips_invalid_pairs():
    """Entity pairs with empty names are skipped."""
    mock_result = _make_search_result(entities=[_make_entity("e1")])

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    mock_breaker.call = AsyncMock(return_value=mock_result)

    mock_path_client = MagicMock()
    mock_path_client.lookup_entity_name = AsyncMock(return_value=None)
    mock_path_client.close = AsyncMock()

    client_instances = [mock_client, mock_path_client]
    call_count = {"n": 0}

    def neo4j_factory():
        idx = min(call_count["n"], len(client_instances) - 1)
        call_count["n"] += 1
        return client_instances[idx]

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", side_effect=neo4j_factory):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(
                    sub_queries=["Q1"],
                    entity_pairs=[["", "B"], ["A"]],  # invalid pairs
                )
                result = await search_knowledge_graph(state)

    assert len(result.path_results) == 0


@pytest.mark.asyncio
async def test_deep_refinement_circuit_open_continues():
    """Circuit open during iterative refinement doesn't crash."""
    from aim.utils.circuit_breaker import CircuitOpenError

    empty_result = _make_search_result(entities=[])

    mock_client = MagicMock()
    mock_client.close = AsyncMock()

    mock_breaker = MagicMock()
    # First call: empty (triggers refinement). Refinement call: circuit open.
    mock_breaker.call = AsyncMock(side_effect=[empty_result, CircuitOpenError("neo4j")])

    with patch("aim.agents.nodes.graph_searcher.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.graph_searcher.Neo4jClient", return_value=mock_client):
            with patch("aim.agents.nodes.graph_searcher.get_breaker", return_value=mock_breaker):
                state = _make_state(
                    reasoning_depth=ReasoningDepth.DEEP,
                    sub_queries=["sparse q"],
                    retries=0,
                )
                result = await search_knowledge_graph(state)

    # Should still complete without error
    assert any("refinement" in step.lower() for step in result.reasoning_steps)
