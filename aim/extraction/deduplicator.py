"""Entity deduplication against the existing knowledge graph.

Before ingesting extracted entities, we check Neo4j for existing nodes
with matching type + normalized name.  If a match exists, we merge
properties (extracted wins for new keys, existing wins for conflicts
unless the extraction confidence is higher).

This prevents the graph from accumulating duplicate nodes like
"Auth Service" / "auth service" / "AuthService".
"""
from __future__ import annotations

import re
import uuid
from typing import Any

import structlog

from aim.extraction.schemas import (
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionResult,
)
from aim.schemas.graph import GraphEntity, GraphRelationship

log = structlog.get_logger(__name__)


def _normalize(name: str) -> str:
    """Normalize a name for fuzzy matching.

    Steps: lowercase → strip → collapse whitespace → remove possessives.
    """
    s = name.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"'s$", "", s)
    return s


class Deduplicator:
    """Deduplicates extracted entities against an existing entity index.

    The index is a dict of ``{normalized_name → (entity_id, properties)}``
    keyed by entity type.  It can be loaded from Neo4j at startup or
    incrementally updated as new entities are ingested.
    """

    def __init__(self) -> None:
        # type → normalized_name → (entity_id, properties, confidence)
        self._index: dict[str, dict[str, tuple[str, dict[str, Any], float]]] = {}

    def load_from_graph_entities(self, entities: list[GraphEntity]) -> None:
        """Pre-seed the index from existing graph entities.

        Call this at startup with the result of a Neo4j entity dump.
        """
        for ent in entities:
            if not ent.labels:
                continue
            etype = next((label for label in ent.labels if label != "Entity"), ent.labels[0])
            name = ent.properties.get("name", "")
            if not name:
                continue
            norm = _normalize(name)
            by_type = self._index.setdefault(etype, {})
            by_type[norm] = (ent.entity_id, ent.properties, ent.score)

        total = sum(len(v) for v in self._index.values())
        log.info("dedup.index_loaded", types=len(self._index), entities=total)

    def deduplicate(
        self,
        result: ExtractionResult,
        *,
        confidence_threshold: float = 0.7,
    ) -> tuple[list[GraphEntity], list[GraphRelationship]]:
        """Convert extracted entities/relationships to graph-ready objects.

        Deduplication strategy:
          1. If an entity with the same type + normalized name exists in the
             index AND the extraction confidence >= threshold, MERGE properties.
          2. Otherwise, create a new entity with a fresh ID.
          3. Register all new/merged entities in the index for intra-batch dedup.

        Returns ``(entities, relationships)`` ready for ``ingest_batch``.
        """
        # Map extracted name → graph entity_id for relationship resolution
        name_to_id: dict[str, str] = {}
        graph_entities: list[GraphEntity] = []

        for ext_ent in result.entities:
            if ext_ent.confidence < confidence_threshold:
                log.debug(
                    "dedup.low_confidence_skip",
                    name=ext_ent.name,
                    confidence=ext_ent.confidence,
                )
                continue

            norm = _normalize(ext_ent.name)
            by_type = self._index.get(ext_ent.entity_type, {})
            existing = by_type.get(norm)

            if existing is not None:
                # ── Merge: update properties, keep existing entity_id ────────
                existing_id, existing_props, existing_conf = existing
                merged_props = {**existing_props}

                # Extracted properties win for NEW keys; existing wins for
                # EXISTING keys unless extraction confidence is higher.
                for key, val in ext_ent.properties.items():
                    if key not in merged_props or ext_ent.confidence > existing_conf:
                        merged_props[key] = val

                # Always update the name to the newest canonical form
                merged_props["name"] = ext_ent.name.strip()
                merged_props["source_uri"] = result.source_uri

                graph_ent = GraphEntity(
                    entity_id=existing_id,
                    labels=[ext_ent.entity_type],
                    properties=merged_props,
                    score=max(ext_ent.confidence, existing_conf),
                )

                # Update index
                by_type[norm] = (existing_id, merged_props, graph_ent.score)
                name_to_id[norm] = existing_id

                log.debug("dedup.merged", name=ext_ent.name, entity_id=existing_id)

            else:
                # ── New entity ───────────────────────────────────────────────
                new_id = str(uuid.uuid4())
                props = {
                    "name": ext_ent.name.strip(),
                    "source_uri": result.source_uri,
                    "extraction_confidence": ext_ent.confidence,
                    **ext_ent.properties,
                }
                graph_ent = GraphEntity(
                    entity_id=new_id,
                    labels=[ext_ent.entity_type],
                    properties=props,
                    score=ext_ent.confidence,
                )

                # Register in index
                by_type = self._index.setdefault(ext_ent.entity_type, {})
                by_type[norm] = (new_id, props, ext_ent.confidence)
                name_to_id[norm] = new_id

                log.debug("dedup.new", name=ext_ent.name, entity_id=new_id)

            graph_entities.append(graph_ent)

        # ── Resolve relationships ────────────────────────────────────────────
        graph_rels: list[GraphRelationship] = []

        for ext_rel in result.relationships:
            src_norm = _normalize(ext_rel.source_name)
            tgt_norm = _normalize(ext_rel.target_name)

            src_id = name_to_id.get(src_norm)
            tgt_id = name_to_id.get(tgt_norm)

            if src_id is None or tgt_id is None:
                # Look up in the full index across all types
                if src_id is None:
                    for by_type in self._index.values():
                        if src_norm in by_type:
                            src_id = by_type[src_norm][0]
                            break
                if tgt_id is None:
                    for by_type in self._index.values():
                        if tgt_norm in by_type:
                            tgt_id = by_type[tgt_norm][0]
                            break

            if src_id is None or tgt_id is None:
                log.debug(
                    "dedup.rel_unresolved",
                    source=ext_rel.source_name,
                    target=ext_rel.target_name,
                    rel_type=ext_rel.rel_type,
                )
                continue

            graph_rels.append(
                GraphRelationship(
                    rel_id=str(uuid.uuid4()),
                    rel_type=ext_rel.rel_type,
                    source_id=src_id,
                    target_id=tgt_id,
                    properties={
                        "source_uri": result.source_uri,
                        "extraction_confidence": ext_rel.confidence,
                        "evidence_uri": result.source_uri,
                        **ext_rel.properties,
                    },
                )
            )

        log.info(
            "dedup.complete",
            input_entities=len(result.entities),
            output_entities=len(graph_entities),
            input_rels=len(result.relationships),
            output_rels=len(graph_rels),
        )
        return graph_entities, graph_rels

    def clear(self) -> None:
        """Clear the deduplication index."""
        self._index.clear()


# ── Singleton ────────────────────────────────────────────────────────────────

_dedup_instance: Deduplicator | None = None


def get_deduplicator() -> Deduplicator:
    """Return the process-wide Deduplicator singleton."""
    global _dedup_instance
    if _dedup_instance is None:
        _dedup_instance = Deduplicator()
    return _dedup_instance


def reset_deduplicator() -> None:
    """Reset the singleton — for tests only."""
    global _dedup_instance
    _dedup_instance = None
