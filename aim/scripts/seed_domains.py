"""Additional domain fixtures for AIM seed/eval hardening.

The base Nexus seed proves the enterprise-software shape. These fixtures add
domain independence and scale without hand-maintaining giant literal files.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable


def _id(namespace: str, name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"aim.{namespace}.{name}"))


HEALTHCARE_ENTITIES = [
    {
        "entity_id": _id("healthcare", "patient-amara"),
        "labels": ["Entity", "Patient"],
        "properties": {
            "aim_id": _id("healthcare", "patient-amara"),
            "name": "Patient Amara",
            "title": "CKD cohort patient P-1042",
            "description": (
                "Patient P-1042 enrolled in RENAL-AI after elevated ACR. "
                "Her treatment changed after the study arm showed reduced "
                "kidney-function decline for similar high-risk patients."
            ),
            "domain": "healthcare",
            "tenant_id": "demo-healthcare",
            "visibility": "internal",
            "created_at": "2025-01-12T09:00:00Z",
            "updated_at": "2025-04-03T09:00:00Z",
        },
    },
    {
        "entity_id": _id("healthcare", "study-renal-ai"),
        "labels": ["Entity", "Study"],
        "properties": {
            "aim_id": _id("healthcare", "study-renal-ai"),
            "name": "RENAL-AI Study",
            "title": "RENAL-AI longitudinal nephrology study",
            "description": (
                "Prospective study linking remote monitoring, medication "
                "adherence, and outcome trajectories for chronic kidney disease."
            ),
            "domain": "healthcare",
            "tenant_id": "demo-healthcare",
            "visibility": "internal",
            "created_at": "2024-10-01T09:00:00Z",
            "updated_at": "2025-03-15T09:00:00Z",
        },
    },
    {
        "entity_id": _id("healthcare", "treatment-sglt2"),
        "labels": ["Entity", "Treatment"],
        "properties": {
            "aim_id": _id("healthcare", "treatment-sglt2"),
            "name": "SGLT2 Renal Protection Protocol",
            "title": "SGLT2 renal-protection treatment protocol",
            "description": (
                "Treatment protocol added after RENAL-AI interim analysis. "
                "Requires renal-panel follow-up and adverse-event monitoring."
            ),
            "domain": "healthcare",
            "tenant_id": "demo-healthcare",
            "visibility": "internal",
            "created_at": "2025-02-20T09:00:00Z",
            "updated_at": "2025-03-29T09:00:00Z",
        },
    },
    {
        "entity_id": _id("healthcare", "outcome-egfr-stable"),
        "labels": ["Entity", "Outcome"],
        "properties": {
            "aim_id": _id("healthcare", "outcome-egfr-stable"),
            "name": "Stable eGFR Outcome",
            "title": "Stable eGFR at 90-day review",
            "description": (
                "90-day review showed stable eGFR and reduced albuminuria after "
                "the SGLT2 protocol, with no severe adverse events recorded."
            ),
            "domain": "healthcare",
            "tenant_id": "demo-healthcare",
            "visibility": "internal",
            "created_at": "2025-04-05T09:00:00Z",
            "updated_at": "2025-04-05T09:00:00Z",
        },
    },
    {
        "entity_id": _id("healthcare", "clinician-rana"),
        "labels": ["Entity", "Clinician", "Person"],
        "properties": {
            "aim_id": _id("healthcare", "clinician-rana"),
            "name": "Dr. Meera Rana",
            "title": "Principal Investigator",
            "description": (
                "Principal investigator for RENAL-AI. Approved the SGLT2 "
                "protocol amendment after the safety-board review."
            ),
            "domain": "healthcare",
            "tenant_id": "demo-healthcare",
            "visibility": "internal",
            "created_at": "2024-09-15T09:00:00Z",
            "updated_at": "2025-03-29T09:00:00Z",
        },
    },
    {
        "entity_id": _id("healthcare", "protocol-amendment-7"),
        "labels": ["Entity", "Document", "Protocol"],
        "properties": {
            "aim_id": _id("healthcare", "protocol-amendment-7"),
            "name": "Protocol Amendment 7",
            "title": "RENAL-AI Protocol Amendment 7",
            "content": (
                "Amendment 7 supersedes Amendment 4 for high-risk CKD patients. "
                "It authorizes the SGLT2 renal-protection protocol and requires "
                "explicit outcome tracking for eGFR and albuminuria."
            ),
            "domain": "healthcare",
            "tenant_id": "demo-healthcare",
            "visibility": "internal",
            "created_at": "2025-02-18T09:00:00Z",
            "updated_at": "2025-02-18T09:00:00Z",
        },
    },
]


HEALTHCARE_RELATIONSHIPS = [
    {
        "rel_type": "ENROLLED_IN",
        "source_id": _id("healthcare", "patient-amara"),
        "target_id": _id("healthcare", "study-renal-ai"),
        "properties": {"domain": "healthcare"},
    },
    {
        "rel_type": "TESTS_TREATMENT",
        "source_id": _id("healthcare", "study-renal-ai"),
        "target_id": _id("healthcare", "treatment-sglt2"),
        "properties": {"domain": "healthcare"},
    },
    {
        "rel_type": "RECEIVED",
        "source_id": _id("healthcare", "patient-amara"),
        "target_id": _id("healthcare", "treatment-sglt2"),
        "properties": {"domain": "healthcare"},
    },
    {
        "rel_type": "RESULTED_IN",
        "source_id": _id("healthcare", "treatment-sglt2"),
        "target_id": _id("healthcare", "outcome-egfr-stable"),
        "properties": {"domain": "healthcare", "confidence": 0.86},
    },
    {
        "rel_type": "APPROVED_BY",
        "source_id": _id("healthcare", "protocol-amendment-7"),
        "target_id": _id("healthcare", "clinician-rana"),
        "properties": {"domain": "healthcare", "source_uri": "irb://renal-ai/amendment-7"},
    },
    {
        "rel_type": "SUPPORTED_BY",
        "source_id": _id("healthcare", "treatment-sglt2"),
        "target_id": _id("healthcare", "protocol-amendment-7"),
        "properties": {"domain": "healthcare"},
    },
    {
        "rel_type": "CAUSED_BY",
        "source_id": _id("healthcare", "outcome-egfr-stable"),
        "target_id": _id("healthcare", "treatment-sglt2"),
        "properties": {"domain": "healthcare", "confidence": 0.78},
    },
]


def generate_volume_fixture(node_count: int = 10_000) -> tuple[list[dict], list[dict]]:
    """Generate a deterministic 10k-node scale fixture.

    The fixture forms many shallow clusters plus periodic cross-cluster links,
    which is a better stress profile for graph expansion than a simple chain.
    """
    if node_count < 1:
        return [], []

    entities: list[dict] = []
    relationships: list[dict] = []
    for i in range(node_count):
        cluster = i // 25
        entity_id = _id("volume", f"node-{i:05d}")
        entities.append(
            {
                "entity_id": entity_id,
                "labels": ["Entity", "ScaleNode"],
                "properties": {
                    "aim_id": entity_id,
                    "name": f"Scale Node {i:05d}",
                    "title": f"Scale fixture node {i:05d}",
                    "description": (
                        f"Deterministic volume-test node {i:05d} in cluster {cluster}. "
                        "Used for retrieval latency, traversal fan-out, and UI graph stress."
                    ),
                    "domain": "scale",
                    "cluster": cluster,
                    "tenant_id": "demo-scale",
                    "visibility": "internal",
                    "created_at": "2025-01-01T00:00:00Z",
                },
            }
        )
        if i > 0 and i % 25:
            relationships.append(
                {
                    "rel_type": "LINKS_TO",
                    "source_id": entity_id,
                    "target_id": _id("volume", f"node-{i - 1:05d}"),
                    "properties": {"domain": "scale", "cluster": cluster},
                }
            )
        if i >= 25 and i % 25 == 0:
            relationships.append(
                {
                    "rel_type": "DEPENDS_ON",
                    "source_id": entity_id,
                    "target_id": _id("volume", f"node-{i - 25:05d}"),
                    "properties": {"domain": "scale", "cross_cluster": True},
                }
            )

    return entities, relationships


def extend_seed(
    entities: Iterable[dict],
    relationships: Iterable[dict],
    *,
    include_healthcare: bool = False,
    volume_size: int = 0,
) -> tuple[list[dict], list[dict]]:
    out_entities = list(entities)
    out_relationships = list(relationships)

    if include_healthcare:
        out_entities.extend(HEALTHCARE_ENTITIES)
        out_relationships.extend(HEALTHCARE_RELATIONSHIPS)

    if volume_size:
        volume_entities, volume_relationships = generate_volume_fixture(volume_size)
        out_entities.extend(volume_entities)
        out_relationships.extend(volume_relationships)

    return out_entities, out_relationships
