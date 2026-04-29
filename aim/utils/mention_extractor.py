"""Derive MENTIONS edges from entity descriptions.

Phase α.3. Previously, cross-entity references lived in free-text
descriptions ("svc-auth was migrated under ADR-003", "INC-2025-012
hit the feature store") and the only way to reconstruct them was a
regex pass inside the synthesizer at answer time
(``_TICKET_RE`` in aim/agents/nodes/synthesizer.py).

That made the graph pay the retrieval cost without getting the
reasoning benefit: an ADR→Incident link the regex could spot was
invisible to every upstream graph traversal.

This module promotes those textual references into first-class
MENTIONS edges so graph search can follow them. It's intentionally
standalone (pure-python, no DB dependency) so it can run against:

* The seed corpus at seed time (see ``aim/scripts/seed_demo.py``).
* A future MCP ingestion pipeline.
* A test fixture list of dict-shaped entities.

The function is conservative by design:

* Only emits MENTIONS when the source entity's ``description`` or
  ``title`` contains the target entity's ``name`` as a whole token —
  avoids false positives on substring matches.
* Never emits self-references (a node mentioning itself).
* Never duplicates an edge already present in ``existing_relationships``.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# Word-boundary-anchored match. Names like "ADR-001" and "Project Aurora"
# must appear as a standalone token; "Aurora" alone inside another word
# ("Auroral") won't match.
def _make_pattern(name: str) -> re.Pattern[str]:
    # Escape regex metacharacters (the seed names contain "-", ".", etc.).
    # Word boundaries wrap the whole token — re.escape already handles
    # the interior, and \b anchors each end.
    return re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.IGNORECASE)


def _candidate_names(entity: dict[str, Any]) -> list[str]:
    """Extract identifying names to search for when this entity is the
    target of a mention. Longer names win so "Project Aurora" is
    preferred over "Aurora" when both appear on the same entity."""
    props = entity.get("properties", {}) or {}
    names: list[str] = []
    for key in ("name", "title"):
        val = props.get(key)
        if isinstance(val, str) and val.strip():
            names.append(val.strip())
    # De-dup preserving order, then sort by length descending. Longer
    # matches are more specific and get first shot at claiming the span.
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    out.sort(key=len, reverse=True)
    return out


def _searchable_text(entity: dict[str, Any]) -> str:
    props = entity.get("properties", {}) or {}
    parts: list[str] = []
    for key in ("description", "title", "summary"):
        val = props.get(key)
        if isinstance(val, str):
            parts.append(val)
    return "\n".join(parts)


def _confidence_score(
    name: str,
    *,
    is_unique_in_corpus: bool,
) -> float:
    """Heuristic confidence for a derived MENTIONS edge.

    Inputs are deliberately cheap (no LLM, no cross-entity lookups) so
    the derivation stays pure. Three signals:

    * **Length** — longer names are more specific and less likely to be
      false positives. "ADR-2025-008-migration" is far safer than "svc".
      Capped at 0.3 so a 50-char name doesn't swamp other signals.
    * **Corpus uniqueness** — if the matched name maps to exactly one
      entity in the corpus, the edge is unambiguous. If multiple entities
      share the name (e.g. two "Platform team" entries), downgrade.
    * **Token specificity** — names with digits or hyphens (ticket IDs,
      ADR numbers) are structurally specific; a plain word like
      "Auth" benefits less.

    Base 0.4 + at most 0.6 of combined signal → clamped to [0.5, 1.0]
    so every derived edge is at least "probably right", but nothing
    below 0.5 which would collide with hand-authored edges that
    downstream consumers assume carry full confidence.
    """
    length_component = min(0.3, 0.02 * len(name))
    uniqueness_component = 0.2 if is_unique_in_corpus else 0.0
    has_digit_or_hyphen = any(ch.isdigit() or ch == "-" for ch in name)
    specificity_component = 0.1 if has_digit_or_hyphen else 0.0

    raw = 0.4 + length_component + uniqueness_component + specificity_component
    # Clamp to [0.5, 1.0]. Floor of 0.5 keeps derived edges distinguishable
    # from anything below (which we treat as noise). Ceiling at 1.0 mirrors
    # hand-authored edges; derived can match but not exceed.
    return max(0.5, min(1.0, raw))


def derive_mentions(
    entities: Iterable[dict[str, Any]],
    existing_relationships: Iterable[dict[str, Any]] = (),
    rel_type: str = "MENTIONS",
) -> list[dict[str, Any]]:
    """Scan every entity's description/title for references to every
    other entity's name and return a list of MENTIONS rel dicts shaped
    like the seed's ``RELATIONSHIPS`` entries.

    Args:
        entities: dicts with ``entity_id`` and ``properties`` keys
            (the seed's own shape).
        existing_relationships: already-declared rels; MENTIONS edges
            that duplicate one of these (same src/tgt/rel_type) are
            suppressed.
        rel_type: the relationship type to emit. Defaults to "MENTIONS".
            Callers can pass "REFERENCES" for doc-style edges.

    Returns:
        A list of rel dicts. Each dict carries the source entity_id,
        target entity_id, rel_type, and a ``properties`` dict with a
        ``derived`` flag + a numeric ``confidence`` (δ.3) so
        consumers can rank derived edges instead of only filtering
        them.
    """
    entity_list = list(entities)
    # First pass: count how many distinct entities claim each candidate
    # name. A name that resolves uniquely is more trustworthy than one
    # shared across siblings — feeds the uniqueness signal in the
    # confidence score below.
    name_frequency: dict[str, int] = {}
    for e in entity_list:
        if not e.get("entity_id"):
            continue
        for name in _candidate_names(e):
            key = name.lower()
            name_frequency[key] = name_frequency.get(key, 0) + 1

    # Index: lookup-name (lowercased) → target entity_id. When multiple
    # entities share a name (shouldn't happen in a clean corpus, but the
    # adversarial seed intentionally makes "Platform team" ambiguous),
    # we keep the first and skip subsequent — the alternative is an
    # explosion of ambiguous edges.
    name_to_id: dict[str, str] = {}
    for e in entity_list:
        eid = e.get("entity_id")
        if not eid:
            continue
        for name in _candidate_names(e):
            key = name.lower()
            if key not in name_to_id:
                name_to_id[key] = eid

    # Deduplication index of existing edges — we consider (src,tgt,type)
    # the natural key. Property differences don't count as distinct.
    existing: set[tuple[str, str, str]] = set()
    for r in existing_relationships:
        try:
            existing.add((r["source_id"], r["target_id"], r["rel_type"]))
        except KeyError:
            # Malformed rel dicts are skipped silently — this is a
            # derivation helper, not a validator.
            continue

    derived: list[dict[str, Any]] = []
    emitted: set[tuple[str, str, str]] = set()

    for src in entity_list:
        src_id = src.get("entity_id")
        if not src_id:
            continue
        text = _searchable_text(src)
        if not text:
            continue
        # Try each name in the corpus; skip self-references.
        for name, tgt_id in name_to_id.items():
            if tgt_id == src_id:
                continue
            # Compile on demand — Python caches re.compile internally,
            # but we want the exact escape+word-boundary behaviour from
            # _make_pattern. For a ~200 entity corpus this is fine.
            pattern = _make_pattern(name)
            if pattern.search(text):
                key = (src_id, tgt_id, rel_type)
                if key in existing or key in emitted:
                    continue
                emitted.add(key)
                confidence = _confidence_score(
                    name,
                    is_unique_in_corpus=name_frequency.get(name, 1) == 1,
                )
                derived.append({
                    "rel_type": rel_type,
                    "source_id": src_id,
                    "target_id": tgt_id,
                    "properties": {
                        "derived": True,
                        "matched_name": name,
                        "confidence": round(confidence, 3),
                    },
                })

    return derived
