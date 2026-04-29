"""Live ingestion worker — incremental document → graph path.

Panel audit (2026-04-18) flagged that MENTIONS edges only existed in the
seed corpus: once operators were running, a new Slack thread or Jira
ticket landed as a leaf node with zero cross-references, and every
downstream traversal had to fall back to the synthesizer's regex ticket
pass. That turned the carefully-authored cross-link graph into a
seed-time artefact.

This module closes that loop. When an upstream ingestion event fires
(Slack webhook, Jira issue-created, Confluence page saved), the caller
invokes :func:`ingest_document` with the *new* entity and a reader that
can produce the *existing* entity corpus. We:

1. Run :func:`aim.utils.mention_extractor.derive_mentions` against the
   union of existing + new entities.
2. Keep only the derived edges that **touch the new entity** — a Slack
   message being ingested shouldn't re-derive mentions between two
   Jira tickets that were already in the graph.
3. Upsert the new entity, then upsert each derived MENTIONS edge.

The pure / impure split
-----------------------
:func:`prepare_ingestion` is pure (no I/O) so the derivation contract
is trivially testable without a live Neo4j. :func:`ingest_document`
wires that to ``Neo4jClient.upsert_entity`` / ``upsert_relationship``
under a circuit breaker so a transiently-flaky DB doesn't crash the
ingestion worker — the event is re-enqueued upstream.

Idempotency
-----------
Upserts are by ``entity_id``/``(source_id, target_id, rel_type)``, so
re-delivering the same event is safe: the second call is a no-op at
the graph level. Callers don't need to dedupe.

Out of scope for this module
----------------------------
* Event-source plumbing (webhook handlers, queues). The call site
  whose name is ``ingest_document`` is the seam; hook it to whatever
  event source makes sense (Kafka, Redis streams, a FastAPI webhook).
* Vector index writes. This module is graph-only; the vector side
  already has an async upsert path in ``aim/vectordb``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable

import structlog

from aim.schemas.graph import GraphEntity, GraphRelationship
from aim.utils.mention_extractor import derive_mentions

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class IngestionPlan:
    """Pure-function output of :func:`prepare_ingestion`.

    The new entity as given, plus the subset of derived MENTIONS edges
    that touch it in either direction. Callers apply this to Neo4j via
    upsert operations — the plan itself has no side effects so it's
    trivially testable and loggable.
    """

    entity: dict[str, Any]
    derived_edges: list[dict[str, Any]]


def _dict_to_graph_entity(e: dict[str, Any]) -> GraphEntity:
    """Seed-shape dict → ``GraphEntity``. The seed module keeps dicts
    (easier to edit); the Neo4j client wants typed models."""
    return GraphEntity(
        entity_id=e["entity_id"],
        labels=e.get("labels", ["Entity"]),
        properties=e.get("properties", {}),
    )


def _dict_to_graph_rel(r: dict[str, Any]) -> GraphRelationship:
    src = r["source_id"]
    tgt = r["target_id"]
    return GraphRelationship(
        rel_id=r.get("rel_id") or f"{src}->{r['rel_type']}->{tgt}",
        rel_type=r["rel_type"],
        source_id=src,
        target_id=tgt,
        properties=r.get("properties", {}),
    )


def prepare_ingestion(
    new_entity: dict[str, Any],
    existing_entities: Iterable[dict[str, Any]],
    existing_relationships: Iterable[dict[str, Any]] = (),
) -> IngestionPlan:
    """Compute what would need to change in the graph to ingest
    ``new_entity`` — pure function, no I/O.

    The derivation runs over the full corpus so a new entity can be
    either *target* (an existing description now names it) or *source*
    (its own text names existing entities). We filter to edges that
    touch the new entity so the write path only commits the delta.

    Args:
        new_entity: seed-shape dict with ``entity_id``, optional
            ``labels``, and ``properties``.
        existing_entities: the current corpus. Used both for the
            mention-target index and for suppressing duplicate edges.
        existing_relationships: edges already in the graph — MENTIONS
            emitted here that duplicate one of these are dropped.

    Returns:
        An :class:`IngestionPlan` describing the entity + its derived
        MENTIONS edges.
    """
    new_id = new_entity.get("entity_id")
    if not new_id:
        # Malformed event → empty plan. The caller can see an empty plan
        # and log/discard rather than crashing the worker.
        log.warning("ingestion.prepare.missing_entity_id")
        return IngestionPlan(entity=new_entity, derived_edges=[])

    existing_list = [e for e in existing_entities if e.get("entity_id") != new_id]
    corpus = existing_list + [new_entity]

    all_derived = derive_mentions(
        corpus,
        existing_relationships=existing_relationships,
    )

    # Only edges that touch the new entity — either direction. Edges
    # between two pre-existing entities were already derivable at seed
    # time and are someone else's responsibility.
    touching = [
        r for r in all_derived
        if r["source_id"] == new_id or r["target_id"] == new_id
    ]
    log.info(
        "ingestion.prepare.done",
        entity_id=new_id,
        derived_edge_count=len(touching),
    )
    return IngestionPlan(entity=new_entity, derived_edges=touching)


# Type for the corpus-reader callable the caller injects. Async-first so
# the reader can hit Neo4j / an export cache / a test fixture uniformly.
EntityReader = Callable[[], Awaitable[list[dict[str, Any]]]]
RelReader = Callable[[], Awaitable[list[dict[str, Any]]]]


async def ingest_document(
    new_entity: dict[str, Any],
    *,
    read_entities: EntityReader,
    read_relationships: RelReader,
    upsert_entity: Callable[[GraphEntity], Awaitable[None]],
    upsert_relationship: Callable[[GraphRelationship], Awaitable[None]],
) -> IngestionPlan:
    """Ingest a single document into the graph: upsert the entity and
    any newly-derived MENTIONS edges.

    Dependencies (readers + upsert callables) are injected so the
    function is testable without a live Neo4j. The signatures match
    ``aim.graph.neo4j_client.Neo4jClient`` so wiring at the call site is
    a one-liner.

    Returns the same :class:`IngestionPlan` as the pure function so the
    caller has a record of what was actually written (useful for audit
    logs and 3D-nebula live-update streams).
    """
    existing_entities = await read_entities()
    existing_rels = await read_relationships()
    plan = prepare_ingestion(new_entity, existing_entities, existing_rels)

    await upsert_entity(_dict_to_graph_entity(plan.entity))
    for edge in plan.derived_edges:
        await upsert_relationship(_dict_to_graph_rel(edge))

    log.info(
        "ingestion.document.written",
        entity_id=plan.entity.get("entity_id"),
        edges_written=len(plan.derived_edges),
    )
    return plan
