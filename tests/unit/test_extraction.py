"""Unit tests for the LLM entity extraction pipeline.

Tests cover:
  - Extraction schemas (models, fingerprinting, validation)
  - LLM extractor (prompt → JSON parse → ExtractionResult)
  - Deduplicator (merge, new entity, relationship resolution)
  - Ingest worker extraction wiring (enqueue_extraction, JobKind.EXTRACTION)
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from aim.extraction.schemas import (
    ENTITY_TYPES,
    RELATIONSHIP_TYPES,
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionBatch,
    ExtractionResult,
)
from aim.extraction.deduplicator import Deduplicator, _normalize
from aim.extraction.llm_extractor import (
    LLMExtractor,
    _extract_json,
    _parse_extraction,
    get_extractor,
    reset_extractor,
)
from aim.schemas.graph import GraphEntity
from aim.workers.ingest_worker import IngestWorker, JobKind, JobStatus


# ═══════════════════════════════════════════════════════════════════════════════
# Extraction schemas
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractedEntity:
    def test_normalized_name(self):
        e = ExtractedEntity(entity_type="Person", name="  Alice Smith  ")
        assert e.normalized_name == "alice smith"

    def test_fingerprint_stable(self):
        e1 = ExtractedEntity(entity_type="Service", name="Auth Service")
        e2 = ExtractedEntity(entity_type="Service", name="auth service")
        assert e1.fingerprint == e2.fingerprint

    def test_fingerprint_different_types(self):
        e1 = ExtractedEntity(entity_type="Service", name="Auth")
        e2 = ExtractedEntity(entity_type="Person", name="Auth")
        assert e1.fingerprint != e2.fingerprint

    def test_confidence_clamped(self):
        e = ExtractedEntity(entity_type="Service", name="X", confidence=0.95)
        assert 0.0 <= e.confidence <= 1.0


class TestExtractionResult:
    def test_is_empty_when_no_entities(self):
        r = ExtractionResult()
        assert r.is_empty

    def test_not_empty_with_entity(self):
        r = ExtractionResult(entities=[
            ExtractedEntity(entity_type="Person", name="Alice")
        ])
        assert not r.is_empty


class TestExtractionBatch:
    def test_totals(self):
        batch = ExtractionBatch(results=[
            ExtractionResult(entities=[
                ExtractedEntity(entity_type="Person", name="A"),
                ExtractedEntity(entity_type="Service", name="B"),
            ], relationships=[
                ExtractedRelationship(
                    source_name="A", target_name="B", rel_type="OWNS"
                ),
            ]),
            ExtractionResult(entities=[
                ExtractedEntity(entity_type="Team", name="C"),
            ]),
        ])
        assert batch.total_entities == 3
        assert batch.total_relationships == 1


class TestEntityAndRelTypes:
    def test_known_entity_types(self):
        assert "Person" in ENTITY_TYPES
        assert "Service" in ENTITY_TYPES
        assert "Incident" in ENTITY_TYPES
        assert "Decision" in ENTITY_TYPES

    def test_known_relationship_types(self):
        assert "OWNS" in RELATIONSHIP_TYPES
        assert "DEPENDS_ON" in RELATIONSHIP_TYPES
        assert "CAUSED" in RELATIONSHIP_TYPES


# ═══════════════════════════════════════════════════════════════════════════════
# JSON parsing
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractJson:
    def test_plain_json(self):
        data = '{"entities": [], "relationships": []}'
        assert _extract_json(data) == {"entities": [], "relationships": []}

    def test_markdown_fenced(self):
        data = '```json\n{"entities": [{"name": "A"}]}\n```'
        result = _extract_json(data)
        assert result is not None
        assert result["entities"][0]["name"] == "A"

    def test_leading_text(self):
        data = 'Here are the results:\n{"entities": [], "relationships": []}'
        result = _extract_json(data)
        assert result is not None

    def test_invalid_json_returns_none(self):
        assert _extract_json("not json at all") is None

    def test_array_returns_none(self):
        assert _extract_json("[1, 2, 3]") is None


class TestParseExtraction:
    def test_parses_valid_entities(self):
        data = {
            "entities": [
                {"entity_type": "Person", "name": "Alice", "confidence": 0.9, "properties": {}},
                {"entity_type": "Service", "name": "Auth", "confidence": 0.85, "properties": {"lang": "Go"}},
            ],
            "relationships": [
                {"source_name": "Alice", "target_name": "Auth", "rel_type": "OWNS", "confidence": 0.8},
            ],
        }
        result = _parse_extraction(
            data, allowed_types=ENTITY_TYPES, text_hash="abc", source_uri="test://",
        )
        assert len(result.entities) == 2
        assert len(result.relationships) == 1
        assert result.source_text_hash == "abc"

    def test_filters_unknown_entity_types(self):
        data = {
            "entities": [
                {"entity_type": "Alien", "name": "ET", "confidence": 0.9},
            ],
            "relationships": [],
        }
        result = _parse_extraction(
            data, allowed_types=ENTITY_TYPES, text_hash="x", source_uri="",
        )
        assert len(result.entities) == 0

    def test_filters_unknown_rel_types(self):
        data = {
            "entities": [
                {"entity_type": "Person", "name": "A"},
                {"entity_type": "Person", "name": "B"},
            ],
            "relationships": [
                {"source_name": "A", "target_name": "B", "rel_type": "HUGS"},
            ],
        }
        result = _parse_extraction(
            data, allowed_types=ENTITY_TYPES, text_hash="x", source_uri="",
        )
        assert len(result.relationships) == 0

    def test_deduplicates_within_extraction(self):
        data = {
            "entities": [
                {"entity_type": "Service", "name": "Auth Service"},
                {"entity_type": "Service", "name": "auth service"},  # duplicate
            ],
            "relationships": [],
        }
        result = _parse_extraction(
            data, allowed_types=ENTITY_TYPES, text_hash="x", source_uri="",
        )
        assert len(result.entities) == 1

    def test_drops_rels_with_missing_endpoints(self):
        data = {
            "entities": [
                {"entity_type": "Person", "name": "Alice"},
            ],
            "relationships": [
                {"source_name": "Alice", "target_name": "NonExistent", "rel_type": "OWNS"},
            ],
        }
        result = _parse_extraction(
            data, allowed_types=ENTITY_TYPES, text_hash="x", source_uri="",
        )
        assert len(result.relationships) == 0

    def test_clamps_confidence(self):
        data = {
            "entities": [
                {"entity_type": "Person", "name": "A", "confidence": 1.5},
                {"entity_type": "Person", "name": "B", "confidence": -0.3},
            ],
            "relationships": [],
        }
        result = _parse_extraction(
            data, allowed_types=ENTITY_TYPES, text_hash="x", source_uri="",
        )
        assert result.entities[0].confidence == 1.0
        assert result.entities[1].confidence == 0.0

    def test_skips_invalid_entities(self):
        data = {
            "entities": [
                "not a dict",
                {"entity_type": "Person"},  # missing name
                {"name": "Alice"},  # missing type
            ],
            "relationships": [],
        }
        result = _parse_extraction(
            data, allowed_types=ENTITY_TYPES, text_hash="x", source_uri="",
        )
        assert len(result.entities) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# LLM Extractor
# ═══════════════════════════════════════════════════════════════════════════════


class TestLLMExtractor:
    @pytest.fixture(autouse=True)
    def _reset(self):
        reset_extractor()
        yield
        reset_extractor()

    @pytest.mark.asyncio
    async def test_extract_returns_entities(self):
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "entities": [
                {"entity_type": "Person", "name": "Alice", "confidence": 0.9, "properties": {}},
            ],
            "relationships": [],
        })

        mock_llm = AsyncMock()
        mock_llm.invoke = AsyncMock(return_value=mock_response)

        with patch("aim.extraction.llm_extractor.get_llm_provider", return_value=mock_llm):
            extractor = LLMExtractor()
            result = await extractor.extract("Alice is a senior engineer", source_uri="test://1")

        assert len(result.entities) == 1
        assert result.entities[0].name == "Alice"
        assert result.source_uri == "test://1"

    @pytest.mark.asyncio
    async def test_extract_empty_text_returns_empty(self):
        extractor = LLMExtractor()
        result = await extractor.extract("", source_uri="test://")
        assert result.is_empty

    @pytest.mark.asyncio
    async def test_extract_llm_error_returns_empty(self):
        mock_llm = AsyncMock()
        mock_llm.invoke = AsyncMock(side_effect=RuntimeError("LLM down"))

        with patch("aim.extraction.llm_extractor.get_llm_provider", return_value=mock_llm):
            extractor = LLMExtractor()
            result = await extractor.extract("Some text", source_uri="test://")

        assert result.is_empty

    @pytest.mark.asyncio
    async def test_extract_malformed_json_returns_empty(self):
        mock_response = MagicMock()
        mock_response.content = "This is not valid JSON at all"

        mock_llm = AsyncMock()
        mock_llm.invoke = AsyncMock(return_value=mock_response)

        with patch("aim.extraction.llm_extractor.get_llm_provider", return_value=mock_llm):
            extractor = LLMExtractor()
            result = await extractor.extract("Some text", source_uri="test://")

        assert result.is_empty

    @pytest.mark.asyncio
    async def test_extract_with_entity_types_filter(self):
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "entities": [
                {"entity_type": "Person", "name": "Alice", "confidence": 0.9},
                {"entity_type": "Service", "name": "Auth", "confidence": 0.9},
            ],
            "relationships": [],
        })

        mock_llm = AsyncMock()
        mock_llm.invoke = AsyncMock(return_value=mock_response)

        with patch("aim.extraction.llm_extractor.get_llm_provider", return_value=mock_llm):
            extractor = LLMExtractor()
            result = await extractor.extract(
                "Alice maintains Auth",
                entity_types=["Person"],
            )

        # Only Person should be included (Service is filtered out)
        assert len(result.entities) == 1
        assert result.entities[0].entity_type == "Person"

    @pytest.mark.asyncio
    async def test_extract_augments_explicit_slack_incident_facts(self):
        mock_response = MagicMock()
        mock_response.content = json.dumps({"entities": [], "relationships": []})

        mock_llm = AsyncMock()
        mock_llm.invoke = AsyncMock(return_value=mock_response)

        text = (
            "INC-2025-099 was a config drift in the auth service this morning. "
            "Sarah Chen is leading the response. "
            "We rolled back to the previous config at 11am."
        )

        with patch("aim.extraction.llm_extractor.get_llm_provider", return_value=mock_llm):
            extractor = LLMExtractor()
            result = await extractor.extract(text, source_uri="slack://channel/C/message/1")

        entities = {(e.entity_type, e.name): e for e in result.entities}
        assert ("Incident", "INC-2025-099") in entities
        assert ("Person", "Sarah Chen") in entities
        assert ("Service", "Auth Service") in entities
        assert entities[("Incident", "INC-2025-099")].properties["cause_summary"] == (
            "config drift in the auth service"
        )
        assert entities[("Incident", "INC-2025-099")].properties["resolution_time"] == "11am"
        rels = {(r.source_name, r.rel_type, r.target_name) for r in result.relationships}
        assert ("Sarah Chen", "RESPONDED_TO", "INC-2025-099") in rels
        assert ("INC-2025-099", "AFFECTS", "Auth Service") in rels

    @pytest.mark.asyncio
    async def test_extract_augments_terse_live_slack_incident_facts(self):
        mock_response = MagicMock()
        mock_response.content = json.dumps({"entities": [], "relationships": []})

        mock_llm = AsyncMock()
        mock_llm.invoke = AsyncMock(return_value=mock_response)

        text = (
            "INC-2025-100 just got reported by the SRE team. "
            "Auth service rate limiter started returning 429s after the 10am deploy. "
            "Marcus is on it"
        )

        with patch("aim.extraction.llm_extractor.get_llm_provider", return_value=mock_llm):
            extractor = LLMExtractor()
            result = await extractor.extract(text, source_uri="slack://channel/C/message/2")

        entities = {(e.entity_type, e.name): e for e in result.entities}
        assert ("Incident", "INC-2025-100") in entities
        assert ("Service", "Auth Service") in entities
        assert ("Team", "SRE Team") in entities
        assert ("Person", "Marcus") in entities
        incident_props = entities[("Incident", "INC-2025-100")].properties
        assert incident_props["status_code"] == "429"
        assert incident_props["deploy_time"] == "10am"
        assert incident_props["cause_summary"] == (
            "Auth Service rate limiter returning 429s after the 10am deploy"
        )
        rels = {(r.source_name, r.rel_type, r.target_name) for r in result.relationships}
        assert ("SRE Team", "REPORTED_BY", "INC-2025-100") in rels
        assert ("Marcus", "RESPONDED_TO", "INC-2025-100") in rels
        assert ("INC-2025-100", "IMPACTED", "Auth Service") in rels
        assert ("INC-2025-100", "CAUSED_BY", "Auth Service") in rels

    def test_singleton_factory(self):
        e1 = get_extractor()
        e2 = get_extractor()
        assert e1 is e2

    def test_singleton_reset(self):
        e1 = get_extractor()
        reset_extractor()
        e2 = get_extractor()
        assert e1 is not e2


# ═══════════════════════════════════════════════════════════════════════════════
# Deduplicator
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalize:
    def test_lowercase_strip(self):
        assert _normalize("  Auth Service  ") == "auth service"

    def test_collapse_whitespace(self):
        assert _normalize("Auth   Service") == "auth service"

    def test_strip_possessive(self):
        assert _normalize("Alice's") == "alice"


class TestDeduplicator:
    def test_new_entity_creates_graph_entity(self):
        dedup = Deduplicator()
        result = ExtractionResult(
            entities=[
                ExtractedEntity(entity_type="Service", name="Auth Service", confidence=0.9),
            ],
            source_uri="test://1",
        )
        entities, rels = dedup.deduplicate(result)
        assert len(entities) == 1
        assert entities[0].labels == ["Service"]
        assert entities[0].properties["name"] == "Auth Service"

    def test_merge_existing_entity(self):
        dedup = Deduplicator()
        # Pre-seed with an existing entity
        existing = GraphEntity(
            entity_id="existing-123",
            labels=["Service"],
            properties={"name": "Auth Service", "language": "Go"},
            score=0.8,
        )
        dedup.load_from_graph_entities([existing])

        # Extract the same entity with new properties
        result = ExtractionResult(
            entities=[
                ExtractedEntity(
                    entity_type="Service",
                    name="Auth Service",
                    properties={"team": "Platform"},
                    confidence=0.9,
                ),
            ],
            source_uri="test://2",
        )
        entities, rels = dedup.deduplicate(result)

        assert len(entities) == 1
        assert entities[0].entity_id == "existing-123"
        # New properties added, existing preserved
        assert entities[0].properties["team"] == "Platform"
        assert entities[0].properties["language"] == "Go"

    def test_low_confidence_skipped(self):
        dedup = Deduplicator()
        result = ExtractionResult(
            entities=[
                ExtractedEntity(entity_type="Service", name="Maybe", confidence=0.3),
            ],
        )
        entities, rels = dedup.deduplicate(result, confidence_threshold=0.7)
        assert len(entities) == 0

    def test_relationship_resolution(self):
        dedup = Deduplicator()
        result = ExtractionResult(
            entities=[
                ExtractedEntity(entity_type="Person", name="Alice", confidence=0.9),
                ExtractedEntity(entity_type="Service", name="Auth", confidence=0.9),
            ],
            relationships=[
                ExtractedRelationship(
                    source_name="Alice", target_name="Auth",
                    rel_type="OWNS", confidence=0.85,
                ),
            ],
        )
        entities, rels = dedup.deduplicate(result)
        assert len(rels) == 1
        # Source and target IDs should match the created entities
        entity_ids = {e.entity_id for e in entities}
        assert rels[0].source_id in entity_ids
        assert rels[0].target_id in entity_ids

    def test_unresolved_rel_dropped(self):
        dedup = Deduplicator()
        result = ExtractionResult(
            entities=[
                ExtractedEntity(entity_type="Person", name="Alice", confidence=0.9),
            ],
            relationships=[
                ExtractedRelationship(
                    source_name="Alice", target_name="NonExistent",
                    rel_type="OWNS",
                ),
            ],
        )
        _, rels = dedup.deduplicate(result)
        assert len(rels) == 0

    def test_intra_batch_dedup(self):
        dedup = Deduplicator()
        # Process first result
        r1 = ExtractionResult(
            entities=[
                ExtractedEntity(entity_type="Service", name="Auth", confidence=0.9),
            ],
        )
        e1, _ = dedup.deduplicate(r1)

        # Process second result with the same entity
        r2 = ExtractionResult(
            entities=[
                ExtractedEntity(entity_type="Service", name="auth", confidence=0.85),
            ],
        )
        e2, _ = dedup.deduplicate(r2)

        # Second result should merge with the first
        assert e1[0].entity_id == e2[0].entity_id

    def test_clear(self):
        dedup = Deduplicator()
        result = ExtractionResult(
            entities=[ExtractedEntity(entity_type="Service", name="X", confidence=0.9)],
        )
        dedup.deduplicate(result)
        dedup.clear()
        # After clear, same entity should get a new ID
        e2, _ = dedup.deduplicate(result)
        assert len(e2) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Ingest worker extraction wiring
# ═══════════════════════════════════════════════════════════════════════════════


class TestIngestWorkerExtraction:
    def test_enqueue_extraction_creates_job(self):
        worker = IngestWorker(maxsize=10)
        job_id = worker.enqueue_extraction("Some text about Auth Service", source_uri="test://1")
        job = worker.get_job(job_id)
        assert job is not None
        assert job.kind == JobKind.EXTRACTION
        assert job.raw_text == "Some text about Auth Service"
        assert job.source_uri == "test://1"
        assert job.status == JobStatus.QUEUED

    def test_enqueue_extraction_full_queue(self):
        worker = IngestWorker(maxsize=1)
        worker.enqueue_extraction("Text 1")
        with pytest.raises(RuntimeError, match="capacity"):
            worker.enqueue_extraction("Text 2")

    def test_job_to_dict_extraction_fields(self):
        worker = IngestWorker(maxsize=10)
        job_id = worker.enqueue_extraction("Text", source_uri="test://x")
        job = worker.get_job(job_id)
        d = job.to_dict()
        assert d["kind"] == "extraction"
        assert d["source_uri"] == "test://x"
        assert "entities_extracted" in d

    def test_job_to_dict_ingest_fields(self):
        worker = IngestWorker(maxsize=10)
        from aim.schemas.graph import GraphEntity
        job_id = worker.enqueue(
            [GraphEntity(labels=["Service"], properties={"name": "X"})],
            [],
        )
        job = worker.get_job(job_id)
        d = job.to_dict()
        assert d["kind"] == "ingest"
        assert "entities_extracted" not in d


# ═══════════════════════════════════════════════════════════════════════════════
# Coverage: LLMExtractor.health_check (lines 151-155)
# ═══════════════════════════════════════════════════════════════════════════════


class TestLLMExtractorHealthCheck:
    @pytest.fixture(autouse=True)
    def _reset(self):
        reset_extractor()
        yield
        reset_extractor()

    @pytest.mark.asyncio
    async def test_health_check_returns_true(self):
        mock_llm = AsyncMock()
        mock_llm.health_check = AsyncMock(return_value=True)

        with patch("aim.extraction.llm_extractor.get_llm_provider", return_value=mock_llm):
            extractor = LLMExtractor()
            result = await extractor.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_exception_returns_false(self):
        mock_llm = AsyncMock()
        mock_llm.health_check = AsyncMock(side_effect=RuntimeError("connection refused"))

        with patch("aim.extraction.llm_extractor.get_llm_provider", return_value=mock_llm):
            extractor = LLMExtractor()
            result = await extractor.health_check()

        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# Coverage: _extract_json fallback — JSONDecodeError in regex path (lines 207-208)
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractJsonRegexFallback:
    def test_regex_match_with_invalid_json_returns_none(self):
        """Regex finds a brace-delimited block but it's not valid JSON."""
        raw = "Some leading text {not: valid: json: here} trailing text"
        result = _extract_json(raw)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Coverage: Deduplicator — uncovered lines
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeduplicatorUncoveredLines:
    def test_load_from_graph_entities_skips_empty_labels(self):
        """Line 59: continue on empty labels in load_from_graph_entities()."""
        dedup = Deduplicator()
        entity_no_labels = GraphEntity(
            entity_id="e1",
            labels=[],
            properties={"name": "Orphan"},
            score=0.8,
        )
        entity_with_labels = GraphEntity(
            entity_id="e2",
            labels=["Service"],
            properties={"name": "Auth"},
            score=0.9,
        )
        dedup.load_from_graph_entities([entity_no_labels, entity_with_labels])
        # Only the entity with labels should be indexed
        assert "Service" in dedup._index
        assert len(dedup._index) == 1

    def test_load_from_graph_entities_skips_empty_name(self):
        """Line 63: continue on empty name."""
        dedup = Deduplicator()
        entity_no_name = GraphEntity(
            entity_id="e1",
            labels=["Service"],
            properties={"name": ""},
            score=0.8,
        )
        entity_with_name = GraphEntity(
            entity_id="e2",
            labels=["Service"],
            properties={"name": "Auth"},
            score=0.9,
        )
        dedup.load_from_graph_entities([entity_no_name, entity_with_name])
        assert len(dedup._index.get("Service", {})) == 1

    def test_cross_type_name_lookup_for_relationship_resolution(self):
        """Lines 170-178: Cross-type name lookup for source/target resolution."""
        dedup = Deduplicator()

        # Pre-seed index with entities of different types
        existing_person = GraphEntity(
            entity_id="person-1",
            labels=["Person"],
            properties={"name": "Alice"},
            score=0.9,
        )
        existing_service = GraphEntity(
            entity_id="service-1",
            labels=["Service"],
            properties={"name": "Auth"},
            score=0.9,
        )
        dedup.load_from_graph_entities([existing_person, existing_service])

        # Now extract a relationship between entities that are NOT in the
        # current batch (so name_to_id won't contain them), but DO exist
        # in the cross-type index. Use entities below threshold so they
        # are skipped, forcing resolution via the full index.
        result = ExtractionResult(
            entities=[],
            relationships=[
                ExtractedRelationship(
                    source_name="Alice",
                    target_name="Auth",
                    rel_type="OWNS",
                    confidence=0.9,
                ),
            ],
            source_uri="test://cross",
        )
        _, rels = dedup.deduplicate(result)
        # Relationship should resolve via cross-type index lookup
        assert len(rels) == 1
        assert rels[0].source_id == "person-1"
        assert rels[0].target_id == "service-1"

    def test_unresolved_relationship_logging_and_continue(self):
        """Lines 225-227, 233: Unresolved relationship logged and skipped."""
        dedup = Deduplicator()
        result = ExtractionResult(
            entities=[
                ExtractedEntity(
                    entity_type="Person", name="Alice", confidence=0.9
                ),
            ],
            relationships=[
                ExtractedRelationship(
                    source_name="Alice",
                    target_name="CompletelyUnknown",
                    rel_type="OWNS",
                    confidence=0.8,
                ),
                ExtractedRelationship(
                    source_name="Nobody",
                    target_name="Alice",
                    rel_type="DEPENDS_ON",
                    confidence=0.8,
                ),
            ],
            source_uri="test://unresolved",
        )
        entities, rels = dedup.deduplicate(result)
        # Both relationships should be dropped (unresolved endpoints)
        assert len(entities) == 1
        assert len(rels) == 0
