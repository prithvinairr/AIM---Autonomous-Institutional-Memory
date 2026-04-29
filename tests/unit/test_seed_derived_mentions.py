"""Phase α.3 — seed pipeline augments relationships with derived MENTIONS.

The seed corpus has rich entity descriptions full of cross-references
("svc-auth was migrated under ADR-003", "INC-2025-012 hit the feature
store"). Before this phase, those references only existed as text;
graph traversal couldn't follow them.

This pins that the ``augment_with_derived_mentions`` hook in
``aim/scripts/seed_demo.py`` actually produces edges against the real
Nexus corpus, and that the additive contract holds: hand-authored
relationships survive, new MENTIONS edges appear, count is non-zero
and bounded (no runaway false positives).
"""
from __future__ import annotations

from aim.scripts.seed_demo import (
    ALL_ENTITIES,
    RELATIONSHIPS,
    augment_with_derived_mentions,
)


class TestSeedAugmentation:
    def test_augment_preserves_existing_rels(self):
        """The existing hand-authored edges must not be dropped or
        mutated — augment is strictly additive."""
        augmented = augment_with_derived_mentions(ALL_ENTITIES, RELATIONSHIPS)
        # Every original rel must appear in the augmented list unchanged.
        for original in RELATIONSHIPS:
            assert original in augmented

    def test_augment_adds_at_least_some_mentions(self):
        """The Nexus descriptions are dense with ADR-NNN, INC-YYYY-NNN,
        and project-name references. If we derive zero mentions, the
        extractor isn't doing its job."""
        augmented = augment_with_derived_mentions(ALL_ENTITIES, RELATIONSHIPS)
        derived = [r for r in augmented if r.get("properties", {}).get("derived")]
        assert len(derived) > 0, (
            "Expected at least some derived MENTIONS edges across the "
            "Nexus corpus — the descriptions clearly reference ADRs, "
            "incidents, and projects by name."
        )

    def test_augmented_count_is_bounded(self):
        """Runaway false positives would produce tens of thousands of
        edges — more than entities × entities / 2. Bound sanity check."""
        augmented = augment_with_derived_mentions(ALL_ENTITIES, RELATIONSHIPS)
        ceiling = len(ALL_ENTITIES) * len(ALL_ENTITIES)  # generous
        assert len(augmented) < ceiling

    def test_no_self_mentions(self):
        """An entity whose description names itself must not emit a
        MENTIONS edge to itself."""
        augmented = augment_with_derived_mentions(ALL_ENTITIES, RELATIONSHIPS)
        for r in augmented:
            assert r["source_id"] != r["target_id"], (
                f"Self-reference leaked through: {r}"
            )

    def test_derived_flag_marks_new_edges(self):
        """Every new edge must carry ``properties.derived=True`` so it's
        distinguishable from hand-authored ones during debugging."""
        augmented = augment_with_derived_mentions(ALL_ENTITIES, RELATIONSHIPS)
        derived = [r for r in augmented if r.get("properties", {}).get("derived")]
        for r in derived:
            assert r["rel_type"] == "MENTIONS"
            assert "matched_name" in r["properties"]
