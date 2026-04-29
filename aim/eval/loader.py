"""Ground-truth YAML loader for the A.2 eval harness.

The fixture format is deliberately simple so engineers can hand-author
and diff-review it without losing context to Python dict literals:

    - id: single-001
      question: "Who owns the authentication service?"
      category: single_hop              # single_hop | multi_hop | negative | ambiguous
      hop_depth: 1                      # expected reasoning hops, 0 for negatives
      gold_answer: "Sarah Chen"         # used by the Likert judge + string matcher
      gold_entities:                    # must appear in retrieved graph_nodes
        - svc-auth
        - person-sarah-chen
      gold_path:                        # optional — multi-hop only
        - svc-auth
        - person-sarah-chen
      gold_sources: []                  # optional — specific source_ids that must be cited

Negative questions (no answer in corpus) set ``gold_answer: null`` and
the eval treats "I don't know" as the correct response.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml


def _slug_to_uuid(slug: str) -> str:
    """Project a fixture slug to the same UUID the seed script generates.

    The seed uses ``uuid.uuid5(NAMESPACE_DNS, f"nexus.demo.{slug}")``;
    we mirror that here so retrieved aim_ids and gold_entities live in
    the same namespace and NDCG@10 is meaningful.
    """
    try:
        # Already a UUID? Return as-is.
        return str(uuid.UUID(slug))
    except (ValueError, AttributeError):
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"nexus.demo.{slug}"))


def _project_ids(values) -> tuple[str, ...]:
    return tuple(_slug_to_uuid(str(v)) for v in (values or ()))

Category = Literal["single_hop", "multi_hop", "negative", "ambiguous"]

_VALID_CATEGORIES: set[str] = {"single_hop", "multi_hop", "negative", "ambiguous"}


@dataclass(frozen=True)
class GroundTruthItem:
    """One eval question + its gold answer.

    Frozen so tests can cheaply key items by id and equality-compare.
    """

    id: str
    question: str
    category: Category
    gold_answer: str | None             # None = negative (no answer in corpus)
    hop_depth: int = 0
    gold_entities: tuple[str, ...] = ()
    gold_path: tuple[str, ...] = ()
    gold_sources: tuple[str, ...] = ()

    @property
    def is_negative(self) -> bool:
        return self.category == "negative" or self.gold_answer is None


def load_ground_truth(path: str | Path) -> list[GroundTruthItem]:
    """Parse the YAML fixture into typed records.

    Raises ``ValueError`` on unknown categories or missing required
    fields — bad fixtures should fail at load time, not mid-eval.
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"expected a list at top of {path}, got {type(raw).__name__}")

    items: list[GroundTruthItem] = []
    seen_ids: set[str] = set()
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError(f"row {i} is not a mapping")
        for required in ("id", "question", "category"):
            if required not in row:
                raise ValueError(f"row {i} missing required field '{required}'")
        item_id = str(row["id"])
        if item_id in seen_ids:
            raise ValueError(f"duplicate id {item_id!r} in fixture")
        seen_ids.add(item_id)

        category = row["category"]
        if category not in _VALID_CATEGORIES:
            raise ValueError(
                f"row {item_id}: unknown category {category!r}; "
                f"valid: {sorted(_VALID_CATEGORIES)}"
            )

        gold_answer = row.get("gold_answer")
        # Negative questions must have gold_answer: null. Explicit null
        # forces the fixture author to pick a category, preventing typos.
        if category == "negative" and gold_answer is not None:
            raise ValueError(
                f"row {item_id}: category=negative requires gold_answer: null"
            )
        if category != "negative" and gold_answer is None:
            raise ValueError(
                f"row {item_id}: non-negative category requires a gold_answer"
            )

        items.append(
            GroundTruthItem(
                id=item_id,
                question=str(row["question"]),
                category=category,
                gold_answer=gold_answer,
                hop_depth=int(row.get("hop_depth", 0)),
                gold_entities=_project_ids(row.get("gold_entities", [])),
                gold_path=_project_ids(row.get("gold_path", [])),
                gold_sources=_project_ids(row.get("gold_sources", [])),
            )
        )

    return items


def category_breakdown(items: list[GroundTruthItem]) -> dict[str, int]:
    """Count per category — used by the report to show fixture shape.

    A healthy fixture has roughly 30/40/20/10 single/multi/neg/ambig; if
    the breakdown is skewed, the report calls it out so nobody silently
    evaluates on 95% single-hop and claims "multi-hop winner".
    """
    out: dict[str, int] = {c: 0 for c in _VALID_CATEGORIES}
    for it in items:
        out[it.category] += 1
    return out


def hop_depth_breakdown(items: list[GroundTruthItem]) -> dict[int, int]:
    """Count fixture items by expected hop depth."""
    out: dict[int, int] = {}
    for it in items:
        out[it.hop_depth] = out.get(it.hop_depth, 0) + 1
    return dict(sorted(out.items()))
