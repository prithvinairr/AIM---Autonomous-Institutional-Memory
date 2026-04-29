"""Phase δ.2 — ingest worker cross-corpus MENTIONS derivation.

Panel audit: ``aim.ingestion.live_worker.ingest_document`` was architecturally
sound but operationally orphaned — no webhook/route ever imported it, so in
production a Slack message referencing an already-ingested Jira ticket landed
as a leaf with no MENTIONS edge and every traversal fell back to the
synthesizer's regex ticket pass.

This suite pins the wiring: after the in-batch (δ.1) derivation, the ingest
worker reads a bounded snapshot of the pre-existing Neo4j corpus, runs
``derive_mentions`` over union(snapshot, batch), and appends MENTIONS edges
that touch at least one newly-extracted entity.

Failure modes pinned:
* Edges between two pre-existing entities are *never* re-derived here —
  that's the sweep's job, not the ingest worker's.
* Pre-existing MENTIONS edges are suppressed (dedup contract).
* A Neo4j snapshot failure must NOT crash the worker — δ.1 has already
  landed and δ.2 is strictly best-effort enrichment.
* δ.1 edges appended this turn are themselves passed as ``existing_rels``
  to δ.2 so we don't emit duplicate edges within the same job.
"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from aim.schemas.graph import GraphEntity, GraphRelationship
from aim.workers.ingest_worker import IngestJob, IngestWorker, JobKind


def _ent(eid: str, name: str, description: str = "") -> GraphEntity:
    return GraphEntity(
        entity_id=eid,
        labels=["Entity"],
        properties={"name": name, "description": description},
    )


def _make_job() -> IngestJob:
    return IngestJob(
        job_id="j-cc",
        entities=[],
        relationships=[],
        kind=JobKind.EXTRACTION,
        raw_text="(raw)",
        source_uri="slack://x/y",
    )


@dataclass
class _FakeExtractionResult:
    entities: list
    relationships: list
    is_empty: bool = False


class _FakeExtractor:
    def __init__(self, ents, rels):
        self._ents = ents
        self._rels = rels

    async def extract(self, text, source_uri, entity_types):
        return _FakeExtractionResult(entities=self._ents, relationships=self._rels)


class _FakeDedup:
    def __init__(self, ents, rels):
        self._ents = ents
        self._rels = rels

    def deduplicate(self, result, confidence_threshold):
        return self._ents, self._rels


class _FakeNeo4j:
    """Stand-in for ``Neo4jClient`` — the methods the δ.2 path uses."""

    def __init__(
        self,
        entities: list[dict] | None = None,
        rels: list[dict] | None = None,
        raise_on_snapshot: Exception | None = None,
    ) -> None:
        self._ents = entities or []
        self._rels = rels or []
        self._raise = raise_on_snapshot

    async def list_entity_snapshot(self, limit: int = 10_000):
        if self._raise:
            raise self._raise
        return list(self._ents)

    async def list_relationship_snapshot(self, limit: int = 20_000):
        if self._raise:
            raise self._raise
        return list(self._rels)


class TestCrossCorpusMentions:
    @pytest.mark.asyncio
    async def test_batch_entity_references_existing_corpus_entity(self):
        """The new Slack-extracted entity references an already-ingested
        Jira ticket by name → a MENTIONS edge must appear, even though
        the ticket was NOT in the extracted batch."""
        batch = [_ent("inc-1", "INC-2025-012", "incident traced to ADR-003")]
        existing = [
            {"entity_id": "adr-3", "labels": ["Entity"], "properties": {"name": "ADR-003"}},
        ]

        worker = IngestWorker()
        with patch(
            "aim.extraction.llm_extractor.get_extractor",
            return_value=_FakeExtractor(batch, []),
        ), patch(
            "aim.extraction.deduplicator.get_deduplicator",
            return_value=_FakeDedup(batch, []),
        ), patch(
            "aim.graph.neo4j_client.Neo4jClient",
            return_value=_FakeNeo4j(entities=existing, rels=[]),
        ):
            _, rels = await worker._run_extraction(_make_job())

        mentions = [r for r in rels if r.rel_type == "MENTIONS"]
        assert any(
            m.source_id == "inc-1" and m.target_id == "adr-3" for m in mentions
        ), f"expected inc-1 → adr-3 cross-corpus edge, got {[(m.source_id, m.target_id) for m in mentions]}"

    @pytest.mark.asyncio
    async def test_edges_between_two_pre_existing_entities_are_not_re_derived(self):
        """If Alpha and Bravo both already exist and Alpha's description
        names Bravo, the ingest worker must NOT emit that edge — it's
        the sweep's responsibility, not the per-event path's."""
        batch = [_ent("charlie", "Charlie", "unrelated to anything")]
        existing = [
            {
                "entity_id": "alpha",
                "labels": ["Entity"],
                "properties": {"name": "Alpha", "description": "partners with Bravo"},
            },
            {
                "entity_id": "bravo",
                "labels": ["Entity"],
                "properties": {"name": "Bravo"},
            },
        ]

        worker = IngestWorker()
        with patch(
            "aim.extraction.llm_extractor.get_extractor",
            return_value=_FakeExtractor(batch, []),
        ), patch(
            "aim.extraction.deduplicator.get_deduplicator",
            return_value=_FakeDedup(batch, []),
        ), patch(
            "aim.graph.neo4j_client.Neo4jClient",
            return_value=_FakeNeo4j(entities=existing, rels=[]),
        ):
            _, rels = await worker._run_extraction(_make_job())

        alpha_bravo = [
            r for r in rels
            if r.source_id == "alpha" and r.target_id == "bravo"
        ]
        assert alpha_bravo == [], "edges between two pre-existing entities must not be re-derived"

    @pytest.mark.asyncio
    async def test_existing_edge_in_neo4j_is_suppressed(self):
        """Pre-existing MENTIONS edge in the Neo4j snapshot suppresses the
        duplicate write (dedup contract)."""
        batch = [_ent("inc-1", "INC-2025-012", "traced to ADR-003")]
        existing = [
            {"entity_id": "adr-3", "labels": ["Entity"], "properties": {"name": "ADR-003"}},
        ]
        existing_rels = [
            {"source_id": "inc-1", "target_id": "adr-3", "rel_type": "MENTIONS"},
        ]

        worker = IngestWorker()
        with patch(
            "aim.extraction.llm_extractor.get_extractor",
            return_value=_FakeExtractor(batch, []),
        ), patch(
            "aim.extraction.deduplicator.get_deduplicator",
            return_value=_FakeDedup(batch, []),
        ), patch(
            "aim.graph.neo4j_client.Neo4jClient",
            return_value=_FakeNeo4j(entities=existing, rels=existing_rels),
        ):
            _, rels = await worker._run_extraction(_make_job())

        # Zero new inc-1 → adr-3 MENTIONS edges should be appended.
        cross = [
            r for r in rels
            if r.rel_type == "MENTIONS"
            and r.source_id == "inc-1"
            and r.target_id == "adr-3"
        ]
        assert cross == []

    @pytest.mark.asyncio
    async def test_snapshot_failure_is_best_effort(self, caplog):
        """A Neo4j read failure during δ.2 must NOT crash the worker —
        δ.1's in-batch derivation has already landed and the upstream
        retry loop will handle ingest_batch write failures separately."""
        batch = [
            _ent("inc-1", "INC-2025-012", "references ADR-003 in the body"),
            _ent("adr-3", "ADR-003", "migration decision"),
        ]

        worker = IngestWorker()
        with patch(
            "aim.extraction.llm_extractor.get_extractor",
            return_value=_FakeExtractor(batch, []),
        ), patch(
            "aim.extraction.deduplicator.get_deduplicator",
            return_value=_FakeDedup(batch, []),
        ), patch(
            "aim.graph.neo4j_client.Neo4jClient",
            return_value=_FakeNeo4j(raise_on_snapshot=RuntimeError("neo4j down")),
        ):
            ents, rels = await worker._run_extraction(_make_job())

        # δ.1 still ran — inc-1 and adr-3 are both in the batch, so the
        # in-batch derivation gives us the edge anyway.
        assert ents == batch
        assert any(
            r.rel_type == "MENTIONS"
            and r.source_id == "inc-1"
            and r.target_id == "adr-3"
            for r in rels
        )

    @pytest.mark.asyncio
    async def test_cross_corpus_flag_off_is_noop(self, monkeypatch):
        """When ``live_ingestion_cross_corpus_mentions=False``, Neo4j is
        not read at all — the δ.1 in-batch derivation is the only pass."""
        from aim.config import get_settings

        s = get_settings()
        monkeypatch.setattr(s, "live_ingestion_cross_corpus_mentions", False)

        batch = [_ent("inc-1", "INC-2025-012", "traced to ADR-003")]
        existing = [
            {"entity_id": "adr-3", "labels": ["Entity"], "properties": {"name": "ADR-003"}},
        ]

        neo4j_spy = _FakeNeo4j(entities=existing, rels=[])

        worker = IngestWorker()
        with patch(
            "aim.extraction.llm_extractor.get_extractor",
            return_value=_FakeExtractor(batch, []),
        ), patch(
            "aim.extraction.deduplicator.get_deduplicator",
            return_value=_FakeDedup(batch, []),
        ), patch(
            "aim.graph.neo4j_client.Neo4jClient",
            return_value=neo4j_spy,
        ) as neo_cls:
            _, rels = await worker._run_extraction(_make_job())

        # Neo4jClient must not have been constructed for snapshot at all.
        assert neo_cls.call_count == 0
        # No cross-corpus edge to adr-3.
        assert not any(
            r.rel_type == "MENTIONS"
            and r.target_id == "adr-3"
            for r in rels
        )
