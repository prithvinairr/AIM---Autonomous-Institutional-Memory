"""Query routes — primary AIM interface.

POST /query          → full synchronous reasoning response (auth + rate-limited)
POST /query/stream   → SSE token-by-token streaming with provenance in done event
GET  /query/{id}     → retrieve cached response
"""
from __future__ import annotations

import asyncio
import re
import time
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from aim.agents.reasoning_agent import run_reasoning_agent
from aim.api.deps import AuthDep, hash_api_key, make_rate_limiter
from aim.config import get_settings
from aim.graph.neo4j_client import Neo4jClient
from aim.schemas.provenance import (
    GraphProvenanceEdge,
    GraphProvenanceNode,
    ProvenanceMap,
    SourceReference,
    SourceType,
    SubQueryTrace,
)
from aim.schemas.query import QueryRequest, QueryResponse, StreamChunk
from aim.schemas.query import CostInfo, SubQueryResult
from aim.schemas.conversation import ConversationTurn
from aim.utils.access_control import principal_scope
from aim.utils.cache import get_response_cache
from aim.utils.conversation_store import get_conversation_store
from aim.utils.tenant_keys import tenant_id_for

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/query", tags=["query"])

_QueryRateDep = Depends(make_rate_limiter(requests_per_minute=60))

_INCIDENT_RE = re.compile(r"\bINC-\d{4}-\d+\b")
_EXACT_INCIDENT_TOKENS = (
    "who",
    "what",
    "which",
    "about",
    "summary",
    "status",
    "service",
    "affect",
    "affected",
    "reported",
    "impacted",
    "responder",
    "on it",
    "tell me",
    "explain",
    "lead",
    "leading",
    "fix",
    "fixed",
    "resolved",
    "resolution",
    "what happened",
    "cause",
)


def _is_exact_incident_question(text: str) -> str | None:
    match = _INCIDENT_RE.search(text or "")
    if not match:
        return None
    lowered = text.lower()
    if not any(token in lowered for token in _EXACT_INCIDENT_TOKENS):
        return None
    return match.group(0)


async def _try_exact_incident_response(
    request: QueryRequest,
    *,
    tenant_id: str,
) -> QueryResponse | None:
    """Fast path for operational incident recall.

    This keeps Slack-demo incident questions under the latency budget by
    reading exact structured graph facts directly, while still returning the
    normal QueryResponse/provenance shape.
    """
    incident_id = _is_exact_incident_question(request.query)
    if not incident_id:
        return None

    t0 = time.perf_counter()
    client = Neo4jClient()
    try:
        result = await client.search_exact_name(
            incident_id,
            limit=5,
            rel_limit=30,
            tenant_id=tenant_id,
        )
    finally:
        await client.close()

    if not result.entities:
        provenance = ProvenanceMap(
            query_id=request.query_id,
            sources={},
            graph_nodes=[],
            graph_edges=[],
            sub_query_traces=[
                SubQueryTrace(
                    sub_query_id="exact_incident",
                    sub_query_text=request.query,
                    source_ids=[],
                    graph_node_ids=[],
                )
            ],
            citation_map={},
            overall_confidence=0.20,
            reasoning_steps=[
                f"Exact incident fast path for {incident_id}.",
                "No exact graph record was found; answer was intentionally not inferred from nearby incidents.",
            ],
        )
        return QueryResponse(
            query_id=request.query_id,
            thread_id=request.thread_id,
            original_query=request.query,
            answer=(
                f"I do not have a grounded graph record for {incident_id}. "
                "I will not infer details from nearby or similarly named incidents."
            ),
            sub_query_results=[
                SubQueryResult(
                    sub_query_id="exact_incident",
                    sub_query_text=request.query,
                    graph_hits=0,
                    vector_hits=0,
                    mcp_hits=0,
                )
            ],
            provenance=provenance,
            model_used="structured_exact_incident",
            latency_ms=(time.perf_counter() - t0) * 1000,
            cost_info=CostInfo(),
        )

    entities_by_id = {e.entity_id: e for e in result.entities}
    incident = next(
        (
            e for e in result.entities
            if str(e.properties.get("incident_id") or e.properties.get("name") or "") == incident_id
        ),
        None,
    )
    if incident is None:
        return None

    props = incident.properties or {}
    source = SourceReference(
        source_type=SourceType.NEO4J_GRAPH,
        uri=str(props.get("source_uri") or f"neo4j://node/{incident.entity_id}"),
        title=incident_id,
        content_snippet=str(props.get("summary") or incident_id),
        confidence=0.98,
        metadata={"entity_id": incident.entity_id, "labels": incident.labels},
    )
    cite = f" [SRC:{source.source_id}]"

    lead_names: list[str] = []
    reporter_names: list[str] = []
    impacted_names: list[str] = []
    for rel in result.relationships:
        if rel.rel_type == "RESPONDED_TO" and rel.target_id == incident.entity_id:
            lead = entities_by_id.get(rel.source_id)
            if lead:
                lead_names.append(str(lead.properties.get("name", lead.entity_id)))
            continue
        if rel.rel_type == "REPORTED_BY" and rel.target_id == incident.entity_id:
            reporter = entities_by_id.get(rel.source_id)
            if reporter:
                reporter_names.append(str(reporter.properties.get("name", reporter.entity_id)))
            continue
        if rel.rel_type not in {"IMPACTED", "AFFECTS"} or rel.source_id != incident.entity_id:
            continue
        impacted = entities_by_id.get(rel.target_id)
        if impacted:
            impacted_names.append(str(impacted.properties.get("name", impacted.entity_id)))

    summary = str(props.get("summary") or "").strip()
    cause = str(props.get("cause_summary") or "").strip()
    fix = str(props.get("resolution_action") or "").strip()
    if fix and props.get("resolution_time"):
        fix = f"{fix} at {props['resolution_time']}"

    lowered_query = request.query.lower()
    asks_reporter = any(token in lowered_query for token in ("reported", "reporter"))
    asks_responder = any(
        token in lowered_query
        for token in ("who", "lead", "leading", "responder", "responding", "on it", "owner")
    )
    asks_impact = any(
        token in lowered_query
        for token in ("service", "affect", "affected", "impact", "impacted")
    )
    asks_cause = any(token in lowered_query for token in ("cause", "caused", "why", "trigger"))

    answer_lines = [
        f"{incident_id}: {summary or 'A matching incident record was found, but it has no summary text.'}{cite}"
    ]
    if reporter_names:
        answer_lines.append(f"Reported by: {', '.join(sorted(set(reporter_names)))}.{cite}")
    elif asks_reporter:
        answer_lines.append(
            f"No grounded reporter is recorded for {incident_id}; I will not infer one from nearby incidents.{cite}"
        )
    if lead_names:
        answer_lines.append(f"Response lead: {', '.join(sorted(set(lead_names)))}.{cite}")
    elif asks_responder:
        answer_lines.append(
            f"No grounded responder is recorded for {incident_id}; I will not infer one from nearby incidents.{cite}"
        )
    if impacted_names:
        answer_lines.append(f"Impacted: {', '.join(sorted(set(impacted_names)))}.{cite}")
    elif asks_impact:
        answer_lines.append(
            f"No grounded impacted service is recorded for {incident_id}; I will not infer one from nearby incidents.{cite}"
        )
    if cause:
        answer_lines.append(f"Cause: {cause}.{cite}")
    elif asks_cause:
        answer_lines.append(
            f"No grounded cause is recorded for {incident_id}; I will not infer one from nearby incidents.{cite}"
        )
    if props.get("status_code"):
        answer_lines.append(f"Observed status: HTTP {props['status_code']}.{cite}")
    if props.get("deploy_time"):
        answer_lines.append(f"Timing: after the {props['deploy_time']} deploy.{cite}")
    if fix:
        answer_lines.append(f"Fix: {fix}.{cite}")
    answer = "\n".join(answer_lines)

    graph_nodes = [
        GraphProvenanceNode(
            entity_id=e.entity_id,
            entity_type=next((label for label in e.labels if label != "Entity"), e.labels[0] if e.labels else "Entity"),
            labels=e.labels,
            properties=e.properties,
        )
        for e in result.entities
    ]
    graph_edges = [
        GraphProvenanceEdge(
            source_entity_id=rel.source_id,
            target_entity_id=rel.target_id,
            rel_type=rel.rel_type,
            rel_id=rel.rel_id,
            properties=rel.properties or {},
            confidence=float((rel.properties or {}).get("confidence", 0.95)),
        )
        for rel in result.relationships
    ]
    provenance = ProvenanceMap(
        query_id=request.query_id,
        sources={source.source_id: source},
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        sub_query_traces=[
            SubQueryTrace(
                sub_query_id="exact_incident",
                sub_query_text=request.query,
                source_ids=[source.source_id],
                graph_node_ids=[incident.entity_id],
            )
        ],
        citation_map={line: [source.source_id] for line in answer_lines},
        overall_confidence=0.98,
        reasoning_steps=[
            f"Exact incident fast path for {incident_id}.",
            f"Neo4j exact-name lookup returned {len(result.entities)} entities and {len(result.relationships)} relationships.",
        ],
    )
    return QueryResponse(
        query_id=request.query_id,
        thread_id=request.thread_id,
        original_query=request.query,
        answer=answer,
        sub_query_results=[
            SubQueryResult(
                sub_query_id="exact_incident",
                sub_query_text=request.query,
                graph_hits=len(result.entities),
                vector_hits=0,
                mcp_hits=0,
            )
        ],
        provenance=provenance,
        model_used="structured_exact_incident",
        latency_ms=(time.perf_counter() - t0) * 1000,
        cost_info=CostInfo(),
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Run full AIM reasoning pipeline",
    dependencies=[_QueryRateDep],
)
async def query(
    request: QueryRequest,
    req: Request,
    api_key: AuthDep,
) -> QueryResponse:
    if request.stream:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use POST /query/stream for streaming responses.",
        )

    settings = get_settings()
    cache = get_response_cache()
    conv_store = get_conversation_store()
    cache_key = str(request.query_id)

    log.info(
        "query.received",
        query_id=cache_key,
        thread_id=str(request.thread_id) if request.thread_id else None,
        depth=request.reasoning_depth,
        api_key_hash=hash_api_key(api_key)[:12],
        path=str(req.url.path),
    )

    # Load conversation history if a thread_id is present
    conversation_history: list[dict[str, str]] = []
    if request.thread_id:
        try:
            conversation_history = await conv_store.get_history_for_key(
                request.thread_id, api_key
            )
        except PermissionError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Thread {request.thread_id} belongs to a different API key.",
            )
        log.debug(
            "query.history_loaded",
            thread_id=str(request.thread_id),
            turns=len(conversation_history) // 2,
        )

    # Derive tenant_id from the caller's API key when multi-tenancy is active.
    tenant_id = hash_api_key(api_key) if settings.multi_tenant else ""
    access_principals = principal_scope(
        tenant_id=tenant_id,
        api_key_hash=hash_api_key(api_key),
    )

    fast_response = await _try_exact_incident_response(request, tenant_id=tenant_id)
    if fast_response is not None:
        cache_payload = fast_response.model_dump(mode="json")
        cache_payload["_api_key_hash"] = hash_api_key(api_key)
        await cache.set_tenanted(tenant_id_for(api_key), cache_key, cache_payload)
        log.info(
            "query.completed_fast_path",
            query_id=cache_key,
            latency_ms=fast_response.latency_ms,
            sources=len(fast_response.provenance.sources),
        )
        return fast_response

    try:
        async with asyncio.timeout(settings.route_timeout_seconds):
            response = await run_reasoning_agent(
                query=request.query,
                query_id=request.query_id,
                reasoning_depth=request.reasoning_depth,
                vector_filters=request.filters or None,
                thread_id=request.thread_id,
                conversation_history=conversation_history,
                tenant_id=tenant_id,
                access_principals=access_principals,
            )
    except asyncio.TimeoutError:
        log.error("query.route_timeout", timeout=settings.route_timeout_seconds)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Query timed out after {settings.route_timeout_seconds}s.",
        )
    except Exception as exc:
        log.error("query.failed", error=type(exc).__name__, detail=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Reasoning pipeline failed. Check server logs for details.",
        ) from exc

    # Persist response to cache with ownership metadata
    cache_payload = response.model_dump(mode="json")
    cache_payload["_api_key_hash"] = hash_api_key(api_key)
    # Phase 6: per-tenant response cache — two tenants asking the same
    # question will never share a cache entry even when ``cache_key`` collides.
    await cache.set_tenanted(tenant_id_for(api_key), cache_key, cache_payload)

    # Persist conversation turn if this is a threaded query
    if request.thread_id:
        confidence = (
            response.provenance.overall_confidence
            if response.provenance
            else 0.0
        )
        turn = ConversationTurn(
            query_id=request.query_id,
            user_message=request.query,
            assistant_message=response.answer,
            reasoning_depth=request.reasoning_depth.value,
            latency_ms=response.latency_ms,
            confidence=confidence,
            source_count=len(response.provenance.sources) if response.provenance else 0,
            input_tokens=response.cost_info.input_tokens if response.cost_info else 0,
            output_tokens=response.cost_info.output_tokens if response.cost_info else 0,
        )
        await conv_store.append_turn(
            thread_id=request.thread_id,
            api_key=api_key,
            turn=turn,
        )

    log.info(
        "query.completed",
        query_id=cache_key,
        latency_ms=response.latency_ms,
        sources=len(response.sub_query_results),
        cost_usd=response.cost_info.estimated_cost_usd if response.cost_info else None,
    )

    return response


@router.post(
    "/stream",
    summary="Stream synthesis tokens via Server-Sent Events",
    response_class=StreamingResponse,
    dependencies=[_QueryRateDep],
)
async def query_stream(
    request: QueryRequest,
    req: Request,
    api_key: AuthDep,
) -> StreamingResponse:
    from aim.agents.reasoning_agent import stream_reasoning_agent

    settings = get_settings()
    conv_store = get_conversation_store()
    request_id = req.headers.get("X-Request-ID", "")

    log.info(
        "query_stream.received",
        query_id=str(request.query_id),
        thread_id=str(request.thread_id) if request.thread_id else None,
        api_key_hash=hash_api_key(api_key)[:12],
    )

    # Load conversation history upfront (before entering the generator)
    conversation_history: list[dict[str, str]] = []
    if request.thread_id:
        try:
            conversation_history = await conv_store.get_history_for_key(
                request.thread_id, api_key
            )
        except PermissionError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Thread {request.thread_id} belongs to a different API key.",
            )

    # Derive tenant_id from the caller's API key when multi-tenancy is active.
    tenant_id = hash_api_key(api_key) if settings.multi_tenant else ""
    access_principals = principal_scope(
        tenant_id=tenant_id,
        api_key_hash=hash_api_key(api_key),
    )

    async def _event_generator():
        seq_counter = 0  # monotonic sequence for all emitted chunks

        def _sse(chunk: StreamChunk) -> str:
            nonlocal seq_counter
            # Inject request_id into every chunk for stream-level correlation
            updates: dict = {}
            if request_id and not chunk.request_id:
                updates["request_id"] = request_id
            # Overwrite sequence with the monotonic counter
            updates["sequence"] = seq_counter
            seq_counter += 1
            chunk = chunk.model_copy(update=updates)
            return f"data: {chunk.model_dump_json()}\n\n"

        full_answer_chunks: list[str] = []
        done_chunk: StreamChunk | None = None
        stream_completed = False

        try:
            async with asyncio.timeout(settings.route_timeout_seconds):
                fast_response = await _try_exact_incident_response(
                    request,
                    tenant_id=tenant_id,
                )
                if fast_response is not None:
                    yield _sse(StreamChunk(
                        chunk_type="sub_query",
                        content="Exact incident graph lookup",
                        query_id=request.query_id,
                        sequence=0,
                    ))
                    token_chunk = StreamChunk(
                        chunk_type="token",
                        content=fast_response.answer,
                        query_id=request.query_id,
                        sequence=0,
                    )
                    full_answer_chunks.append(token_chunk.content)
                    yield _sse(token_chunk)
                    done_chunk = StreamChunk(
                        chunk_type="done",
                        content="",
                        query_id=request.query_id,
                        sequence=0,
                        thread_id=fast_response.thread_id,
                        sources=[
                            source.model_dump(mode="json")
                            for source in fast_response.provenance.sources.values()
                        ],
                        confidence=fast_response.provenance.overall_confidence,
                        cost_info=fast_response.cost_info,
                        provenance=fast_response.provenance.model_dump(mode="json"),
                    )
                    stream_completed = True
                    yield _sse(done_chunk)
                else:
                    async for chunk in stream_reasoning_agent(
                        query=request.query,
                        query_id=request.query_id,
                        reasoning_depth=request.reasoning_depth,
                        vector_filters=request.filters or None,
                        thread_id=request.thread_id,
                        conversation_history=conversation_history,
                        tenant_id=tenant_id,
                        access_principals=access_principals,
                    ):
                        if chunk.chunk_type == "token":
                            full_answer_chunks.append(chunk.content)
                        if chunk.chunk_type == "done":
                            done_chunk = chunk
                            stream_completed = True
                        yield _sse(chunk)

        except asyncio.TimeoutError:
            log.error("query_stream.route_timeout", timeout=settings.route_timeout_seconds)
            yield _sse(StreamChunk(
                chunk_type="error",
                content="Stream timed out",
                query_id=request.query_id,
                sequence=0,  # overwritten by _sse
            ))
            return
        except GeneratorExit:
            # Client disconnected — do NOT persist partial answer
            log.warning("query_stream.client_disconnect", query_id=str(request.query_id))
            return
        except Exception as exc:
            log.error("query_stream.error", error=type(exc).__name__)
            yield _sse(StreamChunk(
                chunk_type="error",
                content="Internal error during streaming",
                query_id=request.query_id,
                sequence=0,  # overwritten by _sse
            ))
            return

        # Only persist the conversation turn when the stream completed fully
        # (received a "done" chunk from the agent). Partial answers from
        # disconnects, timeouts, or errors are never saved.
        if request.thread_id and stream_completed and done_chunk and full_answer_chunks:
            full_answer = "".join(full_answer_chunks)
            turn = ConversationTurn(
                query_id=request.query_id,
                user_message=request.query,
                assistant_message=full_answer,
                reasoning_depth=request.reasoning_depth.value,
                latency_ms=0.0,  # not tracked in streaming path
                confidence=done_chunk.confidence or 0.0,
                source_count=len(done_chunk.sources) if done_chunk.sources else 0,
                input_tokens=done_chunk.cost_info.input_tokens if done_chunk.cost_info else 0,
                output_tokens=done_chunk.cost_info.output_tokens if done_chunk.cost_info else 0,
            )
            await conv_store.append_turn(
                thread_id=request.thread_id,
                api_key=api_key,
                turn=turn,
            )

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/{query_id}",
    response_model=QueryResponse,
    summary="Retrieve cached query response",
)
async def get_query(query_id: UUID, api_key: AuthDep) -> QueryResponse:
    cache = get_response_cache()
    # Phase 6: reads from the caller's tenant bucket with a legacy fallback
    # so responses cached before the upgrade stay retrievable.
    raw = await cache.get_tenanted(tenant_id_for(api_key), str(query_id))
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No cached response for query_id={query_id}.",
        )

    # Verify ownership — only the key that created the query can read it
    import hmac as _hmac
    stored_hash = raw.pop("_api_key_hash", None)
    if stored_hash and not _hmac.compare_digest(stored_hash, hash_api_key(api_key)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: query belongs to a different API key.",
        )

    return QueryResponse.model_validate(raw)
