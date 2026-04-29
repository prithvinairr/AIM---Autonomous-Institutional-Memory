"""Graph management routes.

POST   /graph/ingest           → atomic batch upsert (synchronous, transaction)
POST   /graph/ingest/async     → queue for background ingest, returns job_id
GET    /graph/jobs/{job_id}    → poll background ingest job status
POST   /graph/search           → direct graph search
GET    /graph/entity/{id}      → fetch single entity
DELETE /graph/entity/{id}      → DETACH DELETE entity
"""
from __future__ import annotations

import hmac as _hmac
import hashlib

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status

from aim.api.deps import AuthDep, hash_api_key, make_rate_limiter
from aim.config import get_settings
from aim.graph.neo4j_client import Neo4jClient
from aim.schemas.graph import (
    AsyncIngestResponse,
    GraphEntity,
    GraphIngestRequest,
    GraphIngestResponse,
    GraphSearchRequest,
    GraphSearchResult,
    JobStatusResponse,
    GraphRelationship,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/graph", tags=["graph"])

_IngestRateDep = Depends(make_rate_limiter(requests_per_minute=30))


def _attach_source_artifact(
    request: GraphIngestRequest,
) -> tuple[list[GraphEntity], list[GraphRelationship]]:
    """Promote source_uri into a first-class evidence node for direct ingest."""
    entities = list(request.entities)
    relationships = list(request.relationships)
    if not request.source_uri:
        return entities, relationships

    artifact_id = "source:" + hashlib.sha256(request.source_uri.encode()).hexdigest()[:32]
    artifact = GraphEntity(
        entity_id=artifact_id,
        labels=["Entity", "SourceArtifact"],
        properties={
            "name": request.source_uri,
            "source_uri": request.source_uri,
            "provider": request.source_uri.split(":", 1)[0] if ":" in request.source_uri else "direct",
        },
        score=1.0,
    )
    entities.insert(0, artifact)
    relationships = [
        rel.model_copy(
            update={
                "properties": {
                    **(rel.properties or {}),
                    "source_uri": (rel.properties or {}).get("source_uri") or request.source_uri,
                    "evidence_uri": (rel.properties or {}).get("evidence_uri") or request.source_uri,
                    "evidence_artifact_id": (rel.properties or {}).get("evidence_artifact_id")
                    or artifact_id,
                }
            }
        )
        for rel in relationships
    ]
    for entity in request.entities:
        relationships.append(
            GraphRelationship(
                rel_id=f"{artifact_id}->EVIDENCES->{entity.entity_id}",
                rel_type="EVIDENCES",
                source_id=artifact_id,
                target_id=entity.entity_id,
                properties={
                    "source_uri": request.source_uri,
                    "evidence_artifact_id": artifact_id,
                },
            )
        )
    return entities, relationships


# ── Synchronous ingest (small batches, inline) ────────────────────────────────

@router.post(
    "/ingest",
    response_model=GraphIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Atomic batch upsert entities + relationships (single Neo4j transaction)",
    dependencies=[_IngestRateDep],
)
async def ingest(request: GraphIngestRequest, api_key: AuthDep) -> GraphIngestResponse:
    client = Neo4jClient()
    tenant_id = hash_api_key(api_key) if get_settings().multi_tenant else ""
    entities, relationships = _attach_source_artifact(request)
    try:
        nodes_merged, rels_created = await client.ingest_batch(
            entities=entities,
            relationships=relationships,
            tenant_id=tenant_id,
        )
        log.info("graph.ingested", nodes=nodes_merged, rels=rels_created)
        return GraphIngestResponse(
            nodes_created=0,
            nodes_merged=nodes_merged,
            relationships_created=rels_created,
        )
    except Exception as exc:
        log.error("graph.ingest_failed", error=type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Graph ingest failed. The transaction was rolled back.",
        ) from exc


# ── Async ingest (large batches, non-blocking) ────────────────────────────────

@router.post(
    "/ingest/async",
    response_model=AsyncIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue entities + relationships for background ingest (non-blocking)",
    dependencies=[_IngestRateDep],
)
async def ingest_async(
    request: GraphIngestRequest, api_key: AuthDep
) -> AsyncIngestResponse:
    from aim.workers.ingest_worker import get_ingest_worker

    worker = get_ingest_worker()
    tenant_id = hash_api_key(api_key) if get_settings().multi_tenant else ""
    entities, relationships = _attach_source_artifact(request)
    try:
        job_id = worker.enqueue(
            entities,
            relationships,
            api_key_hash=hash_api_key(api_key),
            tenant_id=tenant_id,
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ingest queue is at capacity. Retry in a few seconds.",
        )
    log.info(
        "graph.async_ingest_queued",
        job_id=job_id,
        entities=len(request.entities),
        rels=len(request.relationships),
    )
    return AsyncIngestResponse(
        job_id=job_id,
        entities_queued=len(request.entities),
        relationships_queued=len(request.relationships),
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll the status of a background ingest job",
)
async def get_ingest_job(job_id: str, api_key: AuthDep) -> JobStatusResponse:
    from aim.workers.ingest_worker import get_ingest_worker

    worker = get_ingest_worker()
    job = worker.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingest job {job_id!r} not found.",
        )
    # Verify ownership — only the API key that enqueued the job can poll it
    if job.api_key_hash and not _hmac.compare_digest(job.api_key_hash, hash_api_key(api_key)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: job belongs to a different API key.",
        )
    return JobStatusResponse(**job.to_dict())


# ── Search ────────────────────────────────────────────────────────────────────

@router.post(
    "/search",
    response_model=GraphSearchResult,
    summary="Direct knowledge graph search (bypasses agent pipeline)",
)
async def search_graph(request: GraphSearchRequest, api_key: AuthDep) -> GraphSearchResult:
    client = Neo4jClient()
    tenant_id = hash_api_key(api_key) if get_settings().multi_tenant else ""
    try:
        return await client.search(
            query_text=request.query_text,
            entity_types=request.entity_types,
            max_depth=request.max_depth,
            limit=request.limit,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        log.error("graph.search_failed", error=type(exc).__name__)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Graph search failed."
        ) from exc


# ── Entity CRUD ───────────────────────────────────────────────────────────────

@router.get(
    "/entity/{entity_id}",
    response_model=GraphEntity,
    summary="Fetch a single entity by ID",
)
async def get_entity(entity_id: str, api_key: AuthDep) -> GraphEntity:
    client = Neo4jClient()
    try:
        entity = await client.get_entity(entity_id)
        if entity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Entity {entity_id!r} not found.",
            )
        return entity
    except HTTPException:
        raise
    except Exception as exc:
        log.error("graph.get_entity_failed", entity_id=entity_id, error=type(exc).__name__)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Entity lookup failed."
        ) from exc


@router.delete(
    "/entity/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="DETACH DELETE entity and all its relationships",
)
async def delete_entity(entity_id: str, api_key: AuthDep) -> Response:
    client = Neo4jClient()
    try:
        deleted = await client.delete_entity(entity_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Entity {entity_id!r} not found.",
            )
        log.info("graph.entity_deleted", entity_id=entity_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except Exception as exc:
        log.error(
            "graph.delete_entity_failed", entity_id=entity_id, error=type(exc).__name__
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Entity deletion failed."
        ) from exc
