"""Domain-independent and scale seed fixtures."""
from __future__ import annotations

from aim.scripts.seed_domains import (
    HEALTHCARE_ENTITIES,
    HEALTHCARE_RELATIONSHIPS,
    extend_seed,
    generate_volume_fixture,
)


def test_healthcare_fixture_has_patient_study_treatment_outcome_chain():
    labels_by_id = {
        entity["entity_id"]: set(entity["labels"])
        for entity in HEALTHCARE_ENTITIES
    }
    rel_types = {rel["rel_type"] for rel in HEALTHCARE_RELATIONSHIPS}

    assert any("Patient" in labels for labels in labels_by_id.values())
    assert any("Study" in labels for labels in labels_by_id.values())
    assert any("Treatment" in labels for labels in labels_by_id.values())
    assert any("Outcome" in labels for labels in labels_by_id.values())
    assert {"ENROLLED_IN", "TESTS_TREATMENT", "RESULTED_IN", "CAUSED_BY"} <= rel_types


def test_healthcare_fixture_carries_governance_metadata():
    for entity in HEALTHCARE_ENTITIES:
        props = entity["properties"]
        assert props["domain"] == "healthcare"
        assert props["tenant_id"] == "demo-healthcare"
        assert props["visibility"] == "internal"


def test_volume_fixture_generates_requested_size_and_cross_cluster_links():
    entities, relationships = generate_volume_fixture(10_000)
    assert len(entities) == 10_000
    assert entities[0]["properties"]["aim_id"] == entities[0]["entity_id"]
    assert any(rel["rel_type"] == "DEPENDS_ON" for rel in relationships)
    assert any(rel["properties"].get("cross_cluster") for rel in relationships)


def test_extend_seed_is_additive():
    base_entities = [{"entity_id": "base", "labels": ["Entity"], "properties": {}}]
    base_relationships = [
        {"rel_type": "LINKS_TO", "source_id": "base", "target_id": "base", "properties": {}}
    ]
    entities, relationships = extend_seed(
        base_entities,
        base_relationships,
        include_healthcare=True,
        volume_size=3,
    )

    assert base_entities[0] in entities
    assert base_relationships[0] in relationships
    assert len(entities) == 1 + len(HEALTHCARE_ENTITIES) + 3
