"""Fact-layer helpers for institutional memory.

The graph stores raw entities and relationships, but an institutional memory
engine also needs durable claims: who/what asserted a relationship, what
evidence supports it, whether it is verified, and when it is valid.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from aim.schemas.graph import GraphEntity, GraphRelationship

FACT_EDGE_TYPES = frozenset({
    "ASSERTS",
    "EVIDENCES",
    "OBJECT",
    "SUBJECT",
    "SUPPORTED_BY",
})

_EVIDENCE_GOVERNANCE_KEYS = (
    "tenant_id",
    "visibility",
    "access",
    "acl_principals",
    "allowed_principals",
    "principals_allowed",
    "acl_groups",
    "allowed_groups",
    "classification",
    "data_classification",
)


def is_fact_internal_relationship(rel_type: str) -> bool:
    return rel_type in FACT_EDGE_TYPES


def _stable_fact_id(rel: GraphRelationship) -> str:
    props = rel.properties or {}
    evidence = (
        str(props.get("evidence_artifact_id") or "")
        or str(props.get("evidence_uri") or "")
        or str(props.get("source_uri") or "")
        or rel.rel_id
    )
    raw = f"{rel.source_id}|{rel.rel_type}|{rel.target_id}|{evidence}"
    return "fact:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def _status_from_validity(props: dict[str, Any]) -> str:
    valid_until = props.get("valid_until") or props.get("expires_at")
    if not valid_until:
        return str(props.get("truth_status") or "active")
    try:
        ts = datetime.fromisoformat(str(valid_until).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < datetime.now(timezone.utc):
            return "stale"
    except (TypeError, ValueError):
        pass
    return str(props.get("truth_status") or "active")


def materialize_fact_layer(
    entities: list[GraphEntity],
    relationships: list[GraphRelationship],
) -> tuple[list[GraphEntity], list[GraphRelationship]]:
    """Return entities/relationships augmented with graph-native Fact nodes.

    Each non-internal relationship becomes a (:Fact) node connected to:
      subject -[:ASSERTS]-> fact
      fact -[:SUBJECT]-> subject
      fact -[:OBJECT]-> object
      source_artifact -[:SUPPORTED_BY]-> fact, when evidence_artifact_id exists

    Existing Fact nodes are preserved and IDs are deterministic, so repeated
    ingestion is idempotent under Neo4j MERGE.
    """
    entities_by_id = {e.entity_id: e for e in entities}
    out_entities: dict[str, GraphEntity] = {e.entity_id: e for e in entities}
    out_rels: dict[str, GraphRelationship] = {r.rel_id: r for r in relationships}

    for rel in relationships:
        if is_fact_internal_relationship(rel.rel_type):
            continue
        if rel.source_id.startswith("fact:") or rel.target_id.startswith("fact:"):
            continue

        props = rel.properties or {}
        fact_id = str(props.get("fact_id") or _stable_fact_id(rel))
        subject = entities_by_id.get(rel.source_id)
        obj = entities_by_id.get(rel.target_id)
        subject_name = (
            str((subject.properties or {}).get("name") or (subject.properties or {}).get("title"))
            if subject else rel.source_id
        )
        object_name = (
            str((obj.properties or {}).get("name") or (obj.properties or {}).get("title"))
            if obj else rel.target_id
        )
        statement = str(
            props.get("statement")
            or props.get("claim_text")
            or f"{subject_name} {rel.rel_type} {object_name}"
        )
        confidence = float(
            props.get("confidence")
            or props.get("extraction_confidence")
            or props.get("score")
            or 0.8
        )
        confidence = max(0.0, min(1.0, confidence))
        evidence_artifact_id = str(props.get("evidence_artifact_id") or "")
        evidence_uri = str(props.get("evidence_uri") or props.get("source_uri") or "")
        evidence_entity = entities_by_id.get(evidence_artifact_id) if evidence_artifact_id else None
        evidence_props = evidence_entity.properties if evidence_entity else {}
        inherited_governance = {
            key: (props.get(key) if props.get(key) is not None else evidence_props.get(key))
            for key in _EVIDENCE_GOVERNANCE_KEYS
            if props.get(key) is not None or evidence_props.get(key) is not None
        }

        fact_props = {
            "name": statement,
            "statement": statement,
            "subject_id": rel.source_id,
            "subject_name": subject_name,
            "predicate": rel.rel_type,
            "object_id": rel.target_id,
            "object_name": object_name,
            "source_relationship_id": rel.rel_id,
            "confidence": confidence,
            "verification_status": "verified" if props.get("human_verified") else "inferred",
            "truth_status": _status_from_validity(props),
            "valid_from": props.get("valid_from") or props.get("created_at") or props.get("since") or props.get("timestamp"),
            "valid_until": props.get("valid_until") or props.get("expires_at"),
            "evidence_artifact_id": evidence_artifact_id,
            "evidence_uri": evidence_uri,
            "source_uri": props.get("source_uri") or evidence_uri,
            "extractor_version": props.get("extractor_version") or "unknown",
            **inherited_governance,
        }
        out_entities[fact_id] = GraphEntity(
            entity_id=fact_id,
            labels=["Fact"],
            properties={k: v for k, v in fact_props.items() if v not in ("", None)},
            score=confidence,
        )

        support_props = {
            "fact_id": fact_id,
            "predicate": rel.rel_type,
            "source_relationship_id": rel.rel_id,
            "confidence": confidence,
            "evidence_artifact_id": evidence_artifact_id,
            "evidence_uri": evidence_uri,
            **inherited_governance,
        }
        rel_updates = {
            **props,
            "fact_id": fact_id,
            "confidence": confidence,
            "truth_status": fact_props["truth_status"],
            "verification_status": fact_props["verification_status"],
            **inherited_governance,
        }
        out_rels[rel.rel_id] = rel.model_copy(update={"properties": rel_updates})
        for edge_type, src, tgt in (
            ("ASSERTS", rel.source_id, fact_id),
            ("SUBJECT", fact_id, rel.source_id),
            ("OBJECT", fact_id, rel.target_id),
        ):
            edge_id = f"{src}->{edge_type}->{tgt}"
            out_rels[edge_id] = GraphRelationship(
                rel_id=edge_id,
                rel_type=edge_type,
                source_id=src,
                target_id=tgt,
                properties={k: v for k, v in support_props.items() if v not in ("", None)},
            )
        if evidence_artifact_id:
            edge_id = f"{evidence_artifact_id}->SUPPORTED_BY->{fact_id}"
            out_rels[edge_id] = GraphRelationship(
                rel_id=edge_id,
                rel_type="SUPPORTED_BY",
                source_id=evidence_artifact_id,
                target_id=fact_id,
                properties={k: v for k, v in support_props.items() if v not in ("", None)},
            )

    return list(out_entities.values()), list(out_rels.values())
