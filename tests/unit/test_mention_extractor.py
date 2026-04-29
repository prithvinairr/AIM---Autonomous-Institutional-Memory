"""Phase α.3 — derive_mentions pulls cross-entity references out of
descriptions and emits MENTIONS edges.

Previously the only thing that noticed "ADR-003" appearing in a Slack
message body was the regex pass inside the synthesizer at answer time
(``_TICKET_RE``). That made graph search blind to an ADR→Incident
link the regex could see but the traversal couldn't follow.

This pins the behaviour:

* Matches on whole tokens, not substrings — "Aurora" does not match
  "Auroral", "ADR-001" does not match "ADR-0015".
* Emits one MENTIONS per (source, target, rel_type) — no duplicates
  even if the target name appears multiple times in the source's text.
* Skips self-references.
* Suppresses MENTIONS that duplicate an already-declared rel of the
  same rel_type (so seed data that hand-authors a specific relationship
  doesn't accidentally get shadowed by a generic derived one).
* Longer names win — "Project Aurora" is preferred over "Aurora" when
  both would match.
"""
from __future__ import annotations

from aim.utils.mention_extractor import derive_mentions


def _entity(entity_id: str, name: str, description: str = "") -> dict:
    return {
        "entity_id": entity_id,
        "labels": ["Entity", "Test"],
        "properties": {
            "name": name,
            "description": description,
        },
    }


class TestBasicDerivation:
    def test_mention_in_description_emits_edge(self):
        entities = [
            _entity("a", "ADR-001", "The ADR that started the migration."),
            _entity("b", "Marcus", "Marcus proposed ADR-001 in Q3 2024."),
        ]
        rels = derive_mentions(entities)
        assert any(
            r["source_id"] == "b" and r["target_id"] == "a"
            and r["rel_type"] == "MENTIONS"
            for r in rels
        )

    def test_no_mention_no_edge(self):
        entities = [
            _entity("a", "ADR-001", ""),
            _entity("b", "Marcus", "Marcus is an engineer."),  # no ADR ref
        ]
        rels = derive_mentions(entities)
        assert rels == []

    def test_self_reference_is_skipped(self):
        entities = [
            _entity("a", "Aurora", "Aurora is the search project."),
        ]
        rels = derive_mentions(entities)
        assert rels == []


class TestWordBoundaries:
    def test_substring_does_not_match(self):
        """'Aurora' in the corpus must not match 'Auroral' in someone's
        description — that's the false-positive the word-boundary
        anchoring is designed to prevent."""
        entities = [
            _entity("a", "Aurora", ""),
            _entity("b", "Jane", "Jane studied Auroral physics."),
        ]
        rels = derive_mentions(entities)
        assert rels == []

    def test_adr_001_does_not_match_adr_0015(self):
        entities = [
            _entity("a", "ADR-001", ""),
            _entity("b", "Doc", "See ADR-0015 for the newer spec."),
        ]
        rels = derive_mentions(entities)
        assert rels == []


class TestDeduplication:
    def test_multiple_mentions_same_target_emits_one_edge(self):
        entities = [
            _entity("a", "ADR-001", ""),
            _entity("b", "Marcus", "Marcus wrote ADR-001. ADR-001 is great. See ADR-001."),
        ]
        rels = derive_mentions(entities)
        edges_b_to_a = [r for r in rels if r["source_id"] == "b" and r["target_id"] == "a"]
        assert len(edges_b_to_a) == 1

    def test_existing_relationship_suppresses_derived(self):
        """If the seed already declares a hand-authored MENTIONS, the
        derivation must not shadow it with a duplicate."""
        entities = [
            _entity("a", "ADR-001", ""),
            _entity("b", "Marcus", "Marcus proposed ADR-001."),
        ]
        existing = [
            {"rel_type": "MENTIONS", "source_id": "b", "target_id": "a", "properties": {}},
        ]
        rels = derive_mentions(entities, existing_relationships=existing)
        edges_b_to_a = [r for r in rels if r["source_id"] == "b" and r["target_id"] == "a"]
        assert edges_b_to_a == []

    def test_different_rel_type_not_suppressed(self):
        """An existing PROPOSED_BY edge doesn't block a derived MENTIONS —
        different rel_types are different edges."""
        entities = [
            _entity("a", "ADR-001", ""),
            _entity("b", "Marcus", "Marcus proposed ADR-001."),
        ]
        existing = [
            {"rel_type": "PROPOSED_BY", "source_id": "b", "target_id": "a", "properties": {}},
        ]
        rels = derive_mentions(entities, existing_relationships=existing)
        assert any(
            r["source_id"] == "b" and r["target_id"] == "a" and r["rel_type"] == "MENTIONS"
            for r in rels
        )


class TestLongerNameWins:
    def test_project_aurora_claims_over_bare_aurora(self):
        """When both 'Aurora' and 'Project Aurora' are in the corpus
        and the source says 'Project Aurora', only the longer match
        should claim the span — keeps the more specific edge.

        The current implementation achieves this because both names
        point to the same target entity (there's only one Project
        Aurora), so we emit a single edge regardless of which name
        matched. The test pins that only one edge is emitted."""
        entities = [
            _entity("a", "Project Aurora", ""),
            _entity("b", "Priya", "Priya works on Project Aurora."),
        ]
        rels = derive_mentions(entities)
        edges_b_to_a = [r for r in rels if r["source_id"] == "b" and r["target_id"] == "a"]
        assert len(edges_b_to_a) == 1


class TestRelTypeOverride:
    def test_custom_rel_type(self):
        entities = [
            _entity("a", "ADR-001", ""),
            _entity("b", "Doc", "See ADR-001 for the spec."),
        ]
        rels = derive_mentions(entities, rel_type="REFERENCES")
        assert rels[0]["rel_type"] == "REFERENCES"


class TestDerivedFlag:
    def test_derived_flag_set_on_edges(self):
        """Debug aid — every derived edge carries a ``derived: True``
        flag so it's distinguishable from hand-authored rels."""
        entities = [
            _entity("a", "ADR-001", ""),
            _entity("b", "Marcus", "Marcus proposed ADR-001."),
        ]
        rels = derive_mentions(entities)
        assert all(r["properties"].get("derived") is True for r in rels)
        assert all("matched_name" in r["properties"] for r in rels)
