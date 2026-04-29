"""Phase δ.1 — live ingestion worker.

Panel audit said: "derived MENTIONS only runs at seed time — live Slack
events ingest as leaf nodes with no cross-references." This suite pins
the live path:

* ``prepare_ingestion`` is pure — no DB calls, no state — and computes
  exactly the MENTIONS edges that touch the new entity.
* Edges already present in the graph are suppressed.
* Edges between two pre-existing entities are *not* re-derived (that's
  the seed worker's job, not the live worker's).
* ``ingest_document`` wires the pure plan to injected upserters; both
  entity and each derived edge get written; dependencies are async and
  testable without Neo4j.
* Malformed events (missing entity_id) don't crash the worker — they
  produce an empty plan that the caller can log/discard.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from aim.ingestion.live_worker import (
    IngestionPlan,
    ingest_document,
    prepare_ingestion,
)
from aim.schemas.graph import GraphEntity, GraphRelationship


def _ent(eid: str, name: str, description: str = "", labels: list[str] | None = None) -> dict:
    return {
        "entity_id": eid,
        "labels": labels or ["Entity"],
        "properties": {"name": name, "description": description},
    }


def _rel(src: str, tgt: str, rel_type: str) -> dict:
    return {
        "rel_id": f"{src}-{rel_type}-{tgt}",
        "source_id": src,
        "target_id": tgt,
        "rel_type": rel_type,
    }


class TestPrepareIngestionPure:
    def test_new_entity_as_source_mentions_existing_target(self):
        existing = [_ent("adr-3", "ADR-003")]
        new = _ent(
            "inc-1",
            "INC-2025-012",
            description="incident traced to the rollout of ADR-003",
        )
        plan = prepare_ingestion(new, existing_entities=existing)
        assert isinstance(plan, IngestionPlan)
        assert plan.entity is new
        edges = plan.derived_edges
        assert len(edges) == 1
        assert edges[0]["source_id"] == "inc-1"
        assert edges[0]["target_id"] == "adr-3"
        assert edges[0]["rel_type"] == "MENTIONS"
        assert edges[0]["properties"]["derived"] is True

    def test_new_entity_as_target_existing_mentions_it(self):
        """The new entity is referenced by an existing one's description —
        that edge must be derived even though the existing entity's text
        predates the new entity's arrival."""
        existing = [
            _ent(
                "adr-9",
                "ADR-009",
                description="supersedes the decisions made about Project Aurora",
            ),
        ]
        new = _ent("proj-aur", "Project Aurora")
        plan = prepare_ingestion(new, existing_entities=existing)
        # One edge, existing → new.
        edges = plan.derived_edges
        assert len(edges) == 1
        assert edges[0]["source_id"] == "adr-9"
        assert edges[0]["target_id"] == "proj-aur"

    def test_edges_between_existing_entities_not_re_derived(self):
        """Pre-existing entity A mentions pre-existing entity B in its
        description. That edge is the seed worker's responsibility —
        the *live* worker only emits edges touching the new entity."""
        existing = [
            _ent("a", "Alpha", description="partners with Bravo on the workstream"),
            _ent("b", "Bravo"),
        ]
        new = _ent("c", "Charlie", description="unrelated")
        plan = prepare_ingestion(new, existing_entities=existing)
        # Nothing touches Charlie → empty plan, even though Alpha→Bravo
        # is a derivable edge.
        assert plan.derived_edges == []

    def test_existing_edge_is_suppressed(self):
        """If an operator already hand-authored a MENTIONS edge, the
        derivation must not re-emit it (would be a duplicate write)."""
        existing = [_ent("adr-3", "ADR-003")]
        new = _ent(
            "inc-1",
            "INC-2025-012",
            description="incident traced to ADR-003",
        )
        pre_existing = [_rel("inc-1", "adr-3", "MENTIONS")]
        plan = prepare_ingestion(
            new,
            existing_entities=existing,
            existing_relationships=pre_existing,
        )
        assert plan.derived_edges == []

    def test_missing_entity_id_returns_empty_plan(self):
        """Malformed event (the webhook payload was incomplete) — don't
        crash the worker, just return an empty plan."""
        plan = prepare_ingestion({"properties": {"name": "X"}}, existing_entities=[])
        assert plan.derived_edges == []

    def test_self_reference_not_emitted(self):
        """An entity whose description names itself must not produce a
        self-loop edge."""
        existing = []
        new = _ent(
            "self",
            "Project Self",
            description="Project Self is its own customer",
        )
        plan = prepare_ingestion(new, existing_entities=existing)
        assert all(e["source_id"] != e["target_id"] for e in plan.derived_edges)


class TestIngestDocumentAsync:
    @pytest.mark.asyncio
    async def test_upserts_entity_and_edges(self):
        existing = [_ent("adr-3", "ADR-003")]
        new = _ent(
            "inc-1",
            "INC-2025-012",
            description="rooted in ADR-003 rollout",
        )

        read_entities = AsyncMock(return_value=existing)
        read_relationships = AsyncMock(return_value=[])
        upsert_entity = AsyncMock()
        upsert_relationship = AsyncMock()

        plan = await ingest_document(
            new,
            read_entities=read_entities,
            read_relationships=read_relationships,
            upsert_entity=upsert_entity,
            upsert_relationship=upsert_relationship,
        )

        # Entity upsert called exactly once with a typed GraphEntity.
        upsert_entity.assert_awaited_once()
        (entity_arg,), _ = upsert_entity.call_args
        assert isinstance(entity_arg, GraphEntity)
        assert entity_arg.entity_id == "inc-1"

        # One derived edge → one upsert_relationship call.
        assert upsert_relationship.await_count == 1
        (rel_arg,), _ = upsert_relationship.call_args
        assert isinstance(rel_arg, GraphRelationship)
        assert rel_arg.source_id == "inc-1"
        assert rel_arg.target_id == "adr-3"
        assert rel_arg.rel_type == "MENTIONS"
        assert plan.derived_edges[0]["rel_type"] == "MENTIONS"

    @pytest.mark.asyncio
    async def test_no_derived_edges_still_upserts_entity(self):
        """A document that references nothing still needs to land in the
        graph — as a leaf. The worker must upsert the entity even when
        the plan has no edges."""
        read_entities = AsyncMock(return_value=[])
        read_relationships = AsyncMock(return_value=[])
        upsert_entity = AsyncMock()
        upsert_relationship = AsyncMock()

        new = _ent("lonely", "Lonely Doc", description="no cross-refs")
        await ingest_document(
            new,
            read_entities=read_entities,
            read_relationships=read_relationships,
            upsert_entity=upsert_entity,
            upsert_relationship=upsert_relationship,
        )
        upsert_entity.assert_awaited_once()
        upsert_relationship.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_idempotent_on_re_ingestion(self):
        """Re-delivering the same event: the second call sees the first
        call's edges in ``existing_relationships`` and emits nothing new.
        This is the dedup contract the caller depends on."""
        existing = [_ent("adr-3", "ADR-003")]
        new = _ent("inc-1", "INC-2025-012", description="rooted in ADR-003")
        first_edges: list[dict] = []

        async def read_entities():
            return existing

        async def read_relationships():
            return list(first_edges)

        upsert_entity = AsyncMock()

        async def upsert_rel(rel):
            first_edges.append({
                "source_id": rel.source_id,
                "target_id": rel.target_id,
                "rel_type": rel.rel_type,
            })

        upsert_rel_mock = AsyncMock(side_effect=upsert_rel)

        await ingest_document(
            new,
            read_entities=read_entities,
            read_relationships=read_relationships,
            upsert_entity=upsert_entity,
            upsert_relationship=upsert_rel_mock,
        )
        first_count = upsert_rel_mock.await_count
        assert first_count == 1

        # Second delivery — must be a no-op at the edge level.
        await ingest_document(
            new,
            read_entities=read_entities,
            read_relationships=read_relationships,
            upsert_entity=upsert_entity,
            upsert_relationship=upsert_rel_mock,
        )
        assert upsert_rel_mock.await_count == first_count
