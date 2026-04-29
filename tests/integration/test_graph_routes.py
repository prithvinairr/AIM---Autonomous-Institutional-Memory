"""Integration tests for /api/v1/graph/* routes."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aim.workers.ingest_worker import IngestJob, JobStatus

# ── Fixtures / helpers ────────────────────────────────────────────────────────

_ENTITY = {
    "entity_id": "e-001",
    "labels": ["Person"],
    "properties": {"name": "Alice", "role": "Engineer"},
    "score": 1.0,
}

_REL = {
    "rel_id": "r-001",
    "rel_type": "WORKS_ON",
    "source_id": "e-001",
    "target_id": "e-002",
    "properties": {},
}


# ── POST /graph/ingest (synchronous) ─────────────────────────────────────────

async def test_ingest_returns_201_with_counts(client):
    with patch("aim.api.routes.graph.Neo4jClient") as MockNeo4j:
        MockNeo4j.return_value.ingest_batch = AsyncMock(return_value=(2, 1))

        response = await client.post(
            "/api/v1/graph/ingest",
            json={
                "entities": [_ENTITY, {**_ENTITY, "entity_id": "e-002"}],
                "relationships": [_REL],
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["nodes_merged"] == 2
    assert data["relationships_created"] == 1


async def test_ingest_returns_500_on_neo4j_error(client):
    with patch("aim.api.routes.graph.Neo4jClient") as MockNeo4j:
        MockNeo4j.return_value.ingest_batch = AsyncMock(
            side_effect=RuntimeError("connection refused")
        )

        response = await client.post(
            "/api/v1/graph/ingest",
            json={"entities": [_ENTITY], "relationships": []},
        )

    assert response.status_code == 500
    # Internal error details must not leak to the client
    assert "connection refused" not in response.text


async def test_ingest_requires_auth(test_app):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://testserver"
    ) as anon:
        response = await anon.post(
            "/api/v1/graph/ingest",
            json={"entities": [_ENTITY], "relationships": []},
        )
    assert response.status_code == 401


# ── POST /graph/ingest/async ──────────────────────────────────────────────────

async def test_ingest_async_returns_202_with_job_id(client):
    with patch("aim.workers.ingest_worker.get_ingest_worker") as mock_worker_fn:
        mock_worker = MagicMock()
        mock_worker.enqueue = MagicMock(return_value="job-abc-123")
        mock_worker_fn.return_value = mock_worker

        response = await client.post(
            "/api/v1/graph/ingest/async",
            json={"entities": [_ENTITY], "relationships": []},
        )

    assert response.status_code == 202
    data = response.json()
    assert data["job_id"] == "job-abc-123"
    assert data["status"] == "queued"
    assert data["entities_queued"] == 1
    assert data["relationships_queued"] == 0


async def test_ingest_async_returns_429_when_queue_full(client):
    with patch("aim.workers.ingest_worker.get_ingest_worker") as mock_worker_fn:
        mock_worker = MagicMock()
        mock_worker.enqueue = MagicMock(side_effect=RuntimeError("queue full"))
        mock_worker_fn.return_value = mock_worker

        response = await client.post(
            "/api/v1/graph/ingest/async",
            json={"entities": [_ENTITY], "relationships": []},
        )

    assert response.status_code == 429


# ── GET /graph/jobs/{job_id} ──────────────────────────────────────────────────

async def test_get_job_returns_done_status(client):
    job = IngestJob(
        job_id="job-xyz",
        entities=[],
        relationships=[],
        status=JobStatus.DONE,
        nodes_merged=3,
        rels_created=1,
    )

    with patch("aim.workers.ingest_worker.get_ingest_worker") as mock_worker_fn:
        mock_worker = MagicMock()
        mock_worker.get_job = MagicMock(return_value=job)
        mock_worker_fn.return_value = mock_worker

        response = await client.get("/api/v1/graph/jobs/job-xyz")

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "job-xyz"
    assert data["status"] == "done"
    assert data["nodes_merged"] == 3
    assert data["rels_created"] == 1


async def test_get_job_returns_failed_status_with_error(client):
    job = IngestJob(
        job_id="job-fail",
        entities=[],
        relationships=[],
        status=JobStatus.FAILED,
        error="TimeoutError",
    )

    with patch("aim.workers.ingest_worker.get_ingest_worker") as mock_worker_fn:
        mock_worker = MagicMock()
        mock_worker.get_job = MagicMock(return_value=job)
        mock_worker_fn.return_value = mock_worker

        response = await client.get("/api/v1/graph/jobs/job-fail")

    assert response.status_code == 200
    assert response.json()["error"] == "TimeoutError"


async def test_get_job_returns_404_for_unknown_id(client):
    with patch("aim.workers.ingest_worker.get_ingest_worker") as mock_worker_fn:
        mock_worker = MagicMock()
        mock_worker.get_job = MagicMock(return_value=None)
        mock_worker_fn.return_value = mock_worker

        response = await client.get("/api/v1/graph/jobs/nonexistent")

    assert response.status_code == 404


# ── POST /graph/search ────────────────────────────────────────────────────────

async def test_graph_search_returns_results(client):
    from aim.schemas.graph import GraphSearchResult

    with patch("aim.api.routes.graph.Neo4jClient") as MockNeo4j:
        MockNeo4j.return_value.search = AsyncMock(
            return_value=GraphSearchResult(
                entities=[], relationships=[], total_traversed=0
            )
        )
        response = await client.post(
            "/api/v1/graph/search",
            json={"query_text": "authentication service"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "entities" in data
    assert "relationships" in data


# ── GET /graph/entity/{id} ────────────────────────────────────────────────────

async def test_get_entity_returns_entity(client):
    from aim.schemas.graph import GraphEntity

    with patch("aim.api.routes.graph.Neo4jClient") as MockNeo4j:
        MockNeo4j.return_value.get_entity = AsyncMock(
            return_value=GraphEntity(
                entity_id="e-001",
                labels=["Person"],
                properties={"name": "Alice"},
            )
        )
        response = await client.get("/api/v1/graph/entity/e-001")

    assert response.status_code == 200
    assert response.json()["entity_id"] == "e-001"


async def test_get_entity_returns_404_when_not_found(client):
    with patch("aim.api.routes.graph.Neo4jClient") as MockNeo4j:
        MockNeo4j.return_value.get_entity = AsyncMock(return_value=None)
        response = await client.get("/api/v1/graph/entity/no-such-id")

    assert response.status_code == 404


# ── DELETE /graph/entity/{id} ─────────────────────────────────────────────────

async def test_delete_entity_returns_204(client):
    with patch("aim.api.routes.graph.Neo4jClient") as MockNeo4j:
        MockNeo4j.return_value.delete_entity = AsyncMock(return_value=True)
        response = await client.delete("/api/v1/graph/entity/e-001")

    assert response.status_code == 204


async def test_delete_entity_returns_404_when_not_found(client):
    with patch("aim.api.routes.graph.Neo4jClient") as MockNeo4j:
        MockNeo4j.return_value.delete_entity = AsyncMock(return_value=False)
        response = await client.delete("/api/v1/graph/entity/no-such-id")

    assert response.status_code == 404
