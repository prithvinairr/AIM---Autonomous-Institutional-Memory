"""Phase δ.3 Move 2 — confidence scoring on derived MENTIONS.

Panel audit (2026-04-19) Hallmark 2 quality gap:
    ``derive_mentions`` emits ``{"derived": true, "matched_name": name}``
    but no numeric confidence. Consumers can filter derived edges
    (e.g. exclude them from critical-path reasoning) but can't *rank*
    them — so a ticket with 50 weak MENTIONS looks as authoritative as
    one with 5 explicit ones.

This suite pins the fix: every derived edge now carries a
``confidence`` float in [0.5, 1.0] computed from three cheap
heuristics:

* **Length** — longer names are more specific (cap 0.3).
* **Corpus uniqueness** — single-owner names are unambiguous (+0.2).
* **Token specificity** — digits/hyphens mark ticket-shaped IDs (+0.1).

Tests below verify the relative ordering, the clamp, and backward
compatibility (old consumers that only look at ``derived`` still work).
"""
from __future__ import annotations

from aim.utils.mention_extractor import _confidence_score, derive_mentions


def _ent(eid: str, name: str, description: str = "") -> dict:
    return {
        "entity_id": eid,
        "labels": ["Entity"],
        "properties": {"name": name, "description": description},
    }


class TestConfidenceScoreHeuristic:
    def test_score_is_in_valid_range(self):
        """Every score must clamp to [0.5, 1.0] regardless of inputs."""
        assert 0.5 <= _confidence_score("x", is_unique_in_corpus=False) <= 1.0
        assert 0.5 <= _confidence_score("a" * 500, is_unique_in_corpus=True) <= 1.0

    def test_longer_names_score_higher(self):
        short = _confidence_score("AI", is_unique_in_corpus=True)
        long = _confidence_score("Project Aurora Migration", is_unique_in_corpus=True)
        assert long > short, "longer names should score higher (more specific)"

    def test_unique_name_beats_shared_name(self):
        shared = _confidence_score("Platform", is_unique_in_corpus=False)
        unique = _confidence_score("Platform", is_unique_in_corpus=True)
        assert unique > shared, "unique names should beat ambiguous ones"

    def test_ticket_shaped_ids_score_higher(self):
        """Names with digits or hyphens (ticket IDs like ADR-003,
        INC-2025-012) are structurally more specific than plain words."""
        plain = _confidence_score("Aurora", is_unique_in_corpus=True)
        ticket = _confidence_score("ADR-003", is_unique_in_corpus=True)
        assert ticket > plain, "ticket-shaped IDs should score higher"

    def test_length_component_is_capped(self):
        """A 500-char name must NOT dominate the other signals."""
        cap = _confidence_score("a" * 500, is_unique_in_corpus=False)
        # Length cap is 0.3; base 0.4; no uniqueness; no specificity.
        # → raw 0.7; clamped to 0.7. Must not be 1.0.
        assert cap < 0.9, f"length should cap; got {cap}"


class TestDeriveMentionsEmitsConfidence:
    def test_every_derived_edge_carries_confidence(self):
        """Every edge returned by derive_mentions must have a
        ``confidence`` key in its properties dict."""
        entities = [
            _ent("a", "Alpha", "references Bravo in passing"),
            _ent("b", "Bravo"),
        ]
        derived = derive_mentions(entities)
        assert derived, "expected at least one derived edge"
        for d in derived:
            assert "confidence" in d["properties"]
            assert isinstance(d["properties"]["confidence"], float)
            assert 0.5 <= d["properties"]["confidence"] <= 1.0

    def test_high_specificity_edge_scores_high(self):
        """Long + unique + ticket-shaped → near-ceiling confidence."""
        entities = [
            _ent("inc-1", "INC-2025-012", "traced back to ADR-2025-008-migration"),
            _ent("adr-8", "ADR-2025-008-migration"),
        ]
        derived = derive_mentions(entities)
        # Find the edge from inc-1 → adr-8.
        cross = [d for d in derived if d["source_id"] == "inc-1" and d["target_id"] == "adr-8"]
        assert cross, "expected inc-1 → adr-8 edge"
        assert cross[0]["properties"]["confidence"] >= 0.9

    def test_low_specificity_edge_scores_lower(self):
        """Short + ambiguous + plain word → floor-ish confidence."""
        entities = [
            _ent("a", "Alpha", "the Core depends on everything"),
            _ent("b", "Core"),
            _ent("c", "Core"),  # same name twice → ambiguous
        ]
        derived = derive_mentions(entities)
        assert derived
        scores = [d["properties"]["confidence"] for d in derived]
        assert min(scores) < 0.7, f"ambiguous plain words should score low; got {scores}"

    def test_derived_flag_still_present(self):
        """Backward compat — old consumers reading only ``derived`` must
        still work. Move 2 is strictly additive."""
        entities = [
            _ent("a", "Alpha", "mentions Bravo here"),
            _ent("b", "Bravo"),
        ]
        derived = derive_mentions(entities)
        assert all(d["properties"].get("derived") is True for d in derived)

    def test_matched_name_still_present(self):
        """``matched_name`` is how debug tools trace which regex fired."""
        entities = [
            _ent("a", "Alpha", "references Bravo here"),
            _ent("b", "Bravo"),
        ]
        derived = derive_mentions(entities)
        cross = [d for d in derived if d["source_id"] == "a" and d["target_id"] == "b"]
        assert cross and cross[0]["properties"]["matched_name"].lower() == "bravo"

    def test_unique_name_edge_outranks_ambiguous_edge(self):
        """Given two derived edges from the same source where one targets
        a uniquely-named entity and the other targets a name shared by
        two entities, the unique one's confidence must be higher."""
        entities = [
            _ent("src", "Source", "mentions Unique-ID-A001 and also Platform"),
            _ent("a", "Unique-ID-A001"),
            # Two "Platform" entities — name is ambiguous in the corpus.
            _ent("p1", "Platform"),
            _ent("p2", "Platform"),
        ]
        derived = derive_mentions(entities)
        by_target = {d["target_id"]: d["properties"]["confidence"] for d in derived}
        # src → a (unique + ticket-shaped) should beat src → p1 (plain + ambiguous).
        assert "a" in by_target
        if "p1" in by_target:
            assert by_target["a"] > by_target["p1"]
