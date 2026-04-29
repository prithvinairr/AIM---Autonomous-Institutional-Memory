"""Phase δ.1 — ingest worker augments extracted batches with MENTIONS.

Before this phase, ``IngestWorker._run_extraction`` returned whatever
the LLM extractor + deduplicator gave it. If the extracted batch
contained an entity whose description referenced another extracted
entity, that textual reference never became a graph edge — the next
query had to fall back to the synthesizer's regex ticket pass.

This suite pins the fix: when ``settings.live_ingestion_augment_mentions``
is true (default), the worker applies ``derive_mentions`` to the
extracted batch before returning. Out-of-batch derivation is the
responsibility of ``aim.ingestion.live_worker``.
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
        job_id="j1",
        entities=[],
        relationships=[],
        kind=JobKind.EXTRACTION,
        raw_text="(raw)",
        source_uri="slack://channel/msg",
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


class TestIngestWorkerAugmentation:
    @pytest.mark.asyncio
    async def test_augments_with_mentions_edges(self, monkeypatch):
        """Two extracted entities, one describing the other → a MENTIONS
        edge should be appended to the returned rels."""
        from aim.config import get_settings

        monkeypatch.setattr(get_settings(), "live_ingestion_cross_corpus_mentions", False)

        ents = [
            _ent("inc-1", "INC-2025-012", "incident rooted in ADR-003"),
            _ent("adr-3", "ADR-003", "migration decision"),
        ]
        rels: list[GraphRelationship] = []
        job = _make_job()

        worker = IngestWorker()
        with patch(
            "aim.extraction.llm_extractor.get_extractor",
            return_value=_FakeExtractor(ents, rels),
        ), patch(
            "aim.extraction.deduplicator.get_deduplicator",
            return_value=_FakeDedup(ents, rels),
        ):
            out_ents, out_rels = await worker._run_extraction(job)

        assert out_ents == ents
        # Exactly one MENTIONS edge: inc-1 → adr-3.
        mentions = [r for r in out_rels if r.rel_type == "MENTIONS"]
        assert len(mentions) == 1
        assert mentions[0].source_id == "inc-1"
        assert mentions[0].target_id == "adr-3"
        assert mentions[0].properties.get("derived") is True

    @pytest.mark.asyncio
    async def test_preserves_existing_rels(self):
        """Hand-extracted rels must survive the augmentation pass
        unchanged — δ.1 is strictly additive."""
        ents = [_ent("a", "Alpha", "partners with Bravo"), _ent("b", "Bravo")]
        existing = [
            GraphRelationship(
                rel_id="hand-authored",
                rel_type="OWNS",
                source_id="a",
                target_id="b",
            )
        ]
        job = _make_job()

        worker = IngestWorker()
        with patch(
            "aim.extraction.llm_extractor.get_extractor",
            return_value=_FakeExtractor(ents, existing),
        ), patch(
            "aim.extraction.deduplicator.get_deduplicator",
            return_value=_FakeDedup(ents, existing),
        ):
            _, out_rels = await worker._run_extraction(job)

        assert any(r.rel_id == "hand-authored" for r in out_rels)
        # Plus at least one derived MENTIONS edge.
        assert any(r.rel_type == "MENTIONS" for r in out_rels)

    @pytest.mark.asyncio
    async def test_flag_off_is_noop(self, monkeypatch):
        """When ``live_ingestion_augment_mentions=False``, no MENTIONS
        edges are added — operators can opt out if Neo4j write pressure
        becomes a concern."""
        from aim.config import get_settings

        s = get_settings()
        monkeypatch.setattr(s, "live_ingestion_augment_mentions", False)

        ents = [
            _ent("inc-1", "INC-2025-012", "rooted in ADR-003"),
            _ent("adr-3", "ADR-003"),
        ]
        rels: list[GraphRelationship] = []
        job = _make_job()

        worker = IngestWorker()
        with patch(
            "aim.extraction.llm_extractor.get_extractor",
            return_value=_FakeExtractor(ents, rels),
        ), patch(
            "aim.extraction.deduplicator.get_deduplicator",
            return_value=_FakeDedup(ents, rels),
        ):
            _, out_rels = await worker._run_extraction(job)

        assert not any(r.rel_type == "MENTIONS" for r in out_rels)
