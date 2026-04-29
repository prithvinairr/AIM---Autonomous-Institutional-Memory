"""Tests for exact incident recall guardrails."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from aim.api.routes.query import _try_exact_incident_response
from aim.schemas.graph import GraphEntity, GraphRelationship, GraphSearchResult
from aim.schemas.query import QueryRequest


class _FakeNeo4jClient:
    def __init__(self, result: GraphSearchResult) -> None:
        self._result = result

    async def search_exact_name(self, *args, **kwargs) -> GraphSearchResult:
        return self._result

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_exact_incident_sparse_record_refuses_to_infer_impacted_service():
    incident = GraphEntity(
        entity_id="inc-100",
        labels=["Entity", "Incident"],
        properties={
            "name": "INC-2025-100",
            "incident_id": "INC-2025-100",
            "summary": "INC-2025-100 was reported in Slack.",
        },
    )
    result = GraphSearchResult(
        entities=[incident],
        relationships=[],
        total_traversed=1,
    )
    request = QueryRequest(query="Which service does INC-2025-100 affect?")

    with patch(
        "aim.api.routes.query.Neo4jClient",
        return_value=_FakeNeo4jClient(result),
    ):
        response = await _try_exact_incident_response(request, tenant_id="")

    assert response is not None
    assert response.model_used == "structured_exact_incident"
    assert "No grounded impacted service is recorded for INC-2025-100" in response.answer
    assert "nearby incidents" in response.answer


@pytest.mark.asyncio
async def test_exact_incident_missing_record_does_not_fall_through_to_agent():
    result = GraphSearchResult(
        entities=[],
        relationships=[],
        total_traversed=0,
    )
    request = QueryRequest(query="What caused INC-2025-404?")

    with patch(
        "aim.api.routes.query.Neo4jClient",
        return_value=_FakeNeo4jClient(result),
    ):
        response = await _try_exact_incident_response(request, tenant_id="")

    assert response is not None
    assert response.model_used == "structured_exact_incident"
    assert "do not have a grounded graph record for INC-2025-404" in response.answer
    assert response.provenance.overall_confidence == pytest.approx(0.20)


@pytest.mark.asyncio
async def test_exact_incident_uses_recorded_edges_when_present():
    incident = GraphEntity(
        entity_id="inc-100",
        labels=["Entity", "Incident"],
        properties={
            "name": "INC-2025-100",
            "incident_id": "INC-2025-100",
            "summary": "INC-2025-100 was reported by SRE.",
            "cause_summary": "Auth Service rate limiter returning 429s after deploy",
        },
    )
    service = GraphEntity(
        entity_id="svc-auth",
        labels=["Entity", "Service"],
        properties={"name": "Auth Service"},
    )
    result = GraphSearchResult(
        entities=[incident, service],
        relationships=[
            GraphRelationship(
                rel_id="r1",
                rel_type="IMPACTED",
                source_id="inc-100",
                target_id="svc-auth",
                properties={"confidence": 0.93},
            )
        ],
        total_traversed=3,
    )
    request = QueryRequest(query="Which service does INC-2025-100 affect?")

    with patch(
        "aim.api.routes.query.Neo4jClient",
        return_value=_FakeNeo4jClient(result),
    ):
        response = await _try_exact_incident_response(request, tenant_id="")

    assert response is not None
    assert "Impacted: Auth Service." in response.answer
    assert "No grounded impacted service" not in response.answer
