"""Tests for provenance helpers: citation spans, cross-system entity resolution,
temporal chain, and config validators."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from aim.agents.nodes.synthesizer import (
    _build_institutional_facts,
    _build_temporal_chain,
    build_provenance,
    _compute_citation_spans,
    _resolve_cross_system_entities,
)
from aim.agents.state import AgentState
from aim.schemas.graph import GraphEntity, GraphRelationship
from aim.schemas.provenance import SourceReference, SourceType
from aim.utils.access_control import filter_graph_by_access, filter_sources_by_access, principal_scope
from aim.utils.facts import materialize_fact_layer


# ── Citation spans ───────────────────────────────────────────────────────────


class TestCitationSpans:
    def test_extracts_valid_src_tags(self):
        answer = "The auth service handles tokens. [SRC:src-1] It also does RBAC. [SRC:src-2]"
        clean, spans = _compute_citation_spans(answer, {"src-1", "src-2"})
        # Tags should be stripped from clean answer
        assert "[SRC:" not in clean
        assert "auth service" in clean
        assert len(spans) >= 1

    def test_ignores_unknown_source_ids(self):
        answer = "Some text. [SRC:unknown-id] More text."
        clean, spans = _compute_citation_spans(answer, {"src-1"})
        assert len(spans) == 0
        assert "[SRC:" not in clean

    def test_empty_answer(self):
        clean, spans = _compute_citation_spans("", set())
        assert clean == ""
        assert spans == []

    def test_no_tags(self):
        answer = "A clean answer with no citations at all."
        clean, spans = _compute_citation_spans(answer, {"src-1"})
        assert clean == answer
        assert spans == []

    def test_multiple_tags_same_source(self):
        answer = "Point one. [SRC:src-1] Point two. [SRC:src-1]"
        clean, spans = _compute_citation_spans(answer, {"src-1"})
        assert "[SRC:" not in clean
        assert len(spans) == 2


# ── Cross-system entity resolution ──────────────────────────────────────────


class TestEntityResolution:
    def test_resolves_entities_across_modalities(self):
        sources = {
            "s1": SourceReference(
                source_type=SourceType.NEO4J_GRAPH,
                title="Auth Service",
                confidence=0.9,
                content_snippet="auth service graph data",
            ),
            "s2": SourceReference(
                source_type=SourceType.PINECONE_VECTOR,
                title="Auth Service",
                confidence=0.8,
                content_snippet="auth service vector data",
            ),
            "s3": SourceReference(
                source_type=SourceType.SLACK_MCP,
                title="Different Thing",
                confidence=0.7,
                content_snippet="slack message content",
            ),
        }
        resolved = _resolve_cross_system_entities(sources)
        assert len(resolved) == 1
        assert resolved[0].canonical_name == "Auth Service"
        assert len(resolved[0].source_ids) == 2
        assert len(resolved[0].source_types) == 2

    def test_no_cross_modal_matches(self):
        sources = {
            "s1": SourceReference(source_type=SourceType.NEO4J_GRAPH, title="A", confidence=0.9, content_snippet="a"),
            "s2": SourceReference(source_type=SourceType.PINECONE_VECTOR, title="B", confidence=0.8, content_snippet="b"),
        }
        resolved = _resolve_cross_system_entities(sources)
        assert resolved == []

    def test_same_modality_not_resolved(self):
        sources = {
            "s1": SourceReference(source_type=SourceType.NEO4J_GRAPH, title="X", confidence=0.9, content_snippet="x1"),
            "s2": SourceReference(source_type=SourceType.NEO4J_GRAPH, title="X", confidence=0.8, content_snippet="x2"),
        }
        resolved = _resolve_cross_system_entities(sources)
        assert resolved == []

    def test_empty_sources(self):
        assert _resolve_cross_system_entities({}) == []

    def test_case_insensitive_matching(self):
        sources = {
            "s1": SourceReference(source_type=SourceType.NEO4J_GRAPH, title="Event Bus", confidence=0.9, content_snippet="kafka"),
            "s2": SourceReference(source_type=SourceType.SLACK_MCP, title="event bus", confidence=0.7, content_snippet="slack msg"),
        }
        resolved = _resolve_cross_system_entities(sources)
        assert len(resolved) == 1

    def test_short_titles_ignored(self):
        sources = {
            "s1": SourceReference(source_type=SourceType.NEO4J_GRAPH, title="AB", confidence=0.9, content_snippet="ab1"),
            "s2": SourceReference(source_type=SourceType.SLACK_MCP, title="AB", confidence=0.7, content_snippet="ab2"),
        }
        resolved = _resolve_cross_system_entities(sources)
        assert resolved == []


# ── Temporal chain ───────────────────────────────────────────────────────────


class TestTemporalChain:
    def _state(self) -> AgentState:
        return AgentState(query_id=uuid4(), original_query="test")

    def test_sorts_by_timestamp(self):
        sources = {
            "s1": SourceReference(
                source_type=SourceType.NEO4J_GRAPH,
                title="Old Event",
                confidence=0.8,
                content_snippet="old data",
                metadata={"created_at": "2024-01-01T00:00:00Z"},
            ),
            "s2": SourceReference(
                source_type=SourceType.PINECONE_VECTOR,
                title="New Event",
                confidence=0.9,
                content_snippet="new data",
                metadata={"created_at": "2025-03-01T00:00:00Z"},
            ),
        }
        chain, _, _ = _build_temporal_chain(sources, self._state())
        assert len(chain) == 2
        assert chain[0].summary == "Old Event"
        assert chain[1].summary == "New Event"
        assert chain[0].timestamp < chain[1].timestamp

    def test_empty_sources(self):
        chain, violations, violating_ids = _build_temporal_chain({}, self._state())
        assert chain == []
        assert violations == 0
        assert violating_ids == []

    def test_uses_retrieved_at_as_fallback(self):
        sources = {
            "s1": SourceReference(
                source_type=SourceType.NEO4J_GRAPH,
                title="No timestamp",
                confidence=0.8,
                content_snippet="data without timestamp",
            ),
        }
        chain, _, _ = _build_temporal_chain(sources, self._state())
        assert len(chain) == 1
        assert chain[0].timestamp is not None

    def test_prefers_date_field_over_retrieved_at(self):
        sources = {
            "s1": SourceReference(
                source_type=SourceType.NEO4J_GRAPH,
                title="With date",
                confidence=0.8,
                content_snippet="dated content",
                metadata={"date": "2024-06-15"},
            ),
        }
        chain, _, _ = _build_temporal_chain(sources, self._state())
        assert len(chain) == 1
        # Should use the date field, not retrieved_at
        assert chain[0].timestamp.year == 2024
        assert chain[0].timestamp.month == 6


class TestInstitutionalFacts:
    def test_materializes_fact_nodes_for_semantic_relationships(self):
        entities = [
            GraphEntity(entity_id="svc", labels=["Service"], properties={"name": "Auth Service"}),
            GraphEntity(entity_id="team", labels=["Team"], properties={"name": "Platform"}),
            GraphEntity(
                entity_id="source:slack-1",
                labels=["SourceArtifact", "SlackMessage"],
                properties={"source_uri": "slack://C1/1"},
            ),
        ]
        relationships = [
            GraphRelationship(
                rel_id="r1",
                rel_type="OWNS",
                source_id="team",
                target_id="svc",
                properties={
                    "evidence_artifact_id": "source:slack-1",
                    "evidence_uri": "slack://C1/1",
                    "extraction_confidence": 0.91,
                },
            )
        ]

        out_entities, out_rels = materialize_fact_layer(entities, relationships)

        facts = [e for e in out_entities if "Fact" in e.labels]
        assert len(facts) == 1
        assert facts[0].properties["predicate"] == "OWNS"
        assert facts[0].properties["evidence_artifact_id"] == "source:slack-1"
        assert any(r.rel_type == "SUPPORTED_BY" for r in out_rels)
        assert any(r.rel_type == "ASSERTS" for r in out_rels)

    def test_builds_governed_claims_with_support_sources(self):
        state = AgentState(
            query_id=uuid4(),
            original_query="who owns auth?",
            graph_entities=[
                GraphEntity(entity_id="team", labels=["Team"], properties={"name": "Platform"}),
                GraphEntity(entity_id="svc", labels=["Service"], properties={"name": "Auth Service"}),
            ],
            graph_relationships=[
                GraphRelationship(
                    rel_id="r1",
                    rel_type="OWNS",
                    source_id="team",
                    target_id="svc",
                    properties={
                        "fact_id": "fact:owns",
                        "evidence_artifact_id": "source:slack-1",
                        "evidence_uri": "slack://C1/1",
                        "confidence": 0.93,
                    },
                )
            ],
            sources={
                "src1": SourceReference(
                    source_type=SourceType.SLACK_MCP,
                    uri="slack://C1/1",
                    title="Slack thread",
                    content_snippet="Platform owns Auth Service",
                    confidence=0.9,
                    metadata={"source_artifact_id": "source:slack-1"},
                )
            },
        )

        facts = _build_institutional_facts(state)

        assert len(facts) == 1
        assert facts[0].fact_id == "fact:owns"
        assert facts[0].support_source_ids == ["src1"]
        assert facts[0].truth_status == "active"

    def test_marks_conflicting_claims_as_contested_in_provenance(self):
        state = AgentState(
            query_id=uuid4(),
            original_query="who owns auth?",
            answer="Ownership changed. [SRC:src1]",
            graph_entities=[
                GraphEntity(entity_id="svc", labels=["Service"], properties={"name": "Auth Service"}),
                GraphEntity(entity_id="team-a", labels=["Team"], properties={"name": "Platform"}),
                GraphEntity(entity_id="team-b", labels=["Team"], properties={"name": "Identity"}),
            ],
            graph_relationships=[
                GraphRelationship(
                    rel_id="r1",
                    rel_type="OWNS",
                    source_id="team-a",
                    target_id="svc",
                    properties={"fact_id": "fact:a", "confidence": 0.8},
                ),
                GraphRelationship(
                    rel_id="r2",
                    rel_type="OWNS",
                    source_id="team-b",
                    target_id="svc",
                    properties={"fact_id": "fact:b", "confidence": 0.8},
                ),
            ],
            sources={
                "src1": SourceReference(
                    source_type=SourceType.NEO4J_GRAPH,
                    content_snippet="ownership",
                    confidence=0.8,
                )
            },
        )

        provenance = build_provenance(state, {"seg": ["src1"]}, 0.8)

        assert len(provenance.institutional_facts) == 2
        assert {f.truth_status for f in provenance.institutional_facts} == {"contested"}
        assert all(f.contradicts_fact_ids for f in provenance.institutional_facts)

    def test_authoritative_verified_claim_supersedes_lower_authority_conflict(self):
        state = AgentState(
            query_id=uuid4(),
            original_query="who owns auth?",
            graph_entities=[
                GraphEntity(entity_id="svc", labels=["Service"], properties={"name": "Auth Service"}),
                GraphEntity(entity_id="team-a", labels=["Team"], properties={"name": "Platform"}),
                GraphEntity(entity_id="team-b", labels=["Team"], properties={"name": "Identity"}),
            ],
            graph_relationships=[
                GraphRelationship(
                    rel_id="r1",
                    rel_type="OWNS",
                    source_id="team-a",
                    target_id="svc",
                    properties={
                        "fact_id": "fact:slack",
                        "evidence_uri": "slack://C1/1",
                        "confidence": 0.94,
                    },
                ),
                GraphRelationship(
                    rel_id="r2",
                    rel_type="OWNS",
                    source_id="team-b",
                    target_id="svc",
                    properties={
                        "fact_id": "fact:jira",
                        "evidence_uri": "jira://AIM-42",
                        "confidence": 0.86,
                        "verification_status": "verified",
                    },
                ),
            ],
            sources={
                "src-slack": SourceReference(
                    source_type=SourceType.SLACK_MCP,
                    uri="slack://C1/1",
                    content_snippet="Platform owns Auth",
                    confidence=0.94,
                ),
                "src-jira": SourceReference(
                    source_type=SourceType.JIRA_MCP,
                    uri="jira://AIM-42",
                    content_snippet="Identity owns Auth",
                    confidence=0.86,
                ),
            },
        )

        facts = {fact.fact_id: fact for fact in _build_institutional_facts(state)}

        assert facts["fact:jira"].truth_status == "active"
        assert facts["fact:jira"].winning_fact_id == "fact:jira"
        assert facts["fact:slack"].truth_status == "superseded"
        assert facts["fact:slack"].superseded_by_fact_id == "fact:jira"
        assert facts["fact:jira"].authority_score > facts["fact:slack"].authority_score

    def test_fact_layer_inherits_evidence_acl(self):
        entities = [
            GraphEntity(entity_id="svc", labels=["Service"], properties={"name": "Auth Service"}),
            GraphEntity(entity_id="team", labels=["Team"], properties={"name": "Platform"}),
            GraphEntity(
                entity_id="source:jira",
                labels=["SourceArtifact", "JiraIssue"],
                properties={
                    "source_uri": "jira://AIM-7",
                    "acl_principals": ["api_key:allowed"],
                    "classification": "CONFIDENTIAL",
                },
            ),
        ]
        relationships = [
            GraphRelationship(
                rel_id="r1",
                rel_type="OWNS",
                source_id="team",
                target_id="svc",
                properties={"evidence_artifact_id": "source:jira"},
            )
        ]

        out_entities, _ = materialize_fact_layer(entities, relationships)
        fact = next(e for e in out_entities if "Fact" in e.labels)

        assert fact.properties["acl_principals"] == ["api_key:allowed"]
        assert fact.properties["classification"] == "CONFIDENTIAL"


class TestAccessControl:
    def test_filters_graph_entities_relationships_and_sources_by_principal(self):
        principals = principal_scope(api_key_hash="allowed")
        public = GraphEntity(entity_id="public", labels=["Service"], properties={"name": "Public"})
        private = GraphEntity(
            entity_id="private",
            labels=["Service"],
            properties={"name": "Private", "acl_principals": ["api_key:other"]},
        )
        rel = GraphRelationship(
            rel_id="r1",
            rel_type="DEPENDS_ON",
            source_id="public",
            target_id="private",
            properties={},
        )
        sources = {
            "visible": SourceReference(
                source_type=SourceType.NEO4J_GRAPH,
                content_snippet="visible",
                confidence=0.8,
                metadata={"acl_principals": ["api_key:allowed"]},
            ),
            "hidden": SourceReference(
                source_type=SourceType.NEO4J_GRAPH,
                content_snippet="hidden",
                confidence=0.8,
                metadata={"acl_principals": ["api_key:other"]},
            ),
        }

        entities, relationships = filter_graph_by_access(
            [public, private],
            [rel],
            principals=principals,
        )
        filtered_sources = filter_sources_by_access(sources, principals=principals)

        assert [entity.entity_id for entity in entities] == ["public"]
        assert relationships == []
        assert set(filtered_sources) == {"visible"}


# ── Config validators ────────────────────────────────────────────────────────


class TestConfigValidators:
    def test_valid_llm_provider(self):
        from aim.config import Settings
        # Should not raise for valid providers
        assert Settings._validate_llm_provider("anthropic") == "anthropic"
        assert Settings._validate_llm_provider("openai") == "openai"
        assert Settings._validate_llm_provider("local") == "local"

    def test_invalid_llm_provider(self):
        from aim.config import Settings
        with pytest.raises(ValueError, match="llm_provider"):
            Settings._validate_llm_provider("invalid")

    def test_valid_vector_db_provider(self):
        from aim.config import Settings
        assert Settings._validate_vector_db_provider("pinecone") == "pinecone"
        assert Settings._validate_vector_db_provider("qdrant") == "qdrant"
        assert Settings._validate_vector_db_provider("local") == "local"

    def test_invalid_vector_db_provider(self):
        from aim.config import Settings
        with pytest.raises(ValueError, match="vector_db_provider"):
            Settings._validate_vector_db_provider("weaviate")

    def test_valid_mcp_mode(self):
        from aim.config import Settings
        assert Settings._validate_mcp_mode("live") == "live"
        assert Settings._validate_mcp_mode("indexed") == "indexed"

    def test_invalid_mcp_mode(self):
        from aim.config import Settings
        with pytest.raises(ValueError, match="mcp_mode"):
            Settings._validate_mcp_mode("hybrid")

    def test_valid_embedding_provider(self):
        from aim.config import Settings
        assert Settings._validate_embedding_provider("openai") == "openai"
        assert Settings._validate_embedding_provider("local") == "local"

    def test_invalid_embedding_provider(self):
        from aim.config import Settings
        with pytest.raises(ValueError, match="embedding_provider"):
            Settings._validate_embedding_provider("cohere")
