"""Pin tests for aim.eval.loader — lock YAML validation behaviour.

Uses tmp_path for fixture files. No mocks, no IO beyond tmp_path.
"""
from __future__ import annotations

from pathlib import Path
import uuid

import pytest

from aim.eval import GroundTruthItem, category_breakdown, load_ground_truth


def _seed_uuid(slug: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"nexus.demo.{slug}"))


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "fixture.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_valid_minimal_fixture_loads_with_defaults(tmp_path: Path):
    p = _write(
        tmp_path,
        """
- id: q1
  question: "Who owns auth?"
  category: single_hop
  gold_answer: "Alice"
""",
    )
    items = load_ground_truth(p)
    assert len(items) == 1
    it = items[0]
    assert it.id == "q1"
    assert it.question == "Who owns auth?"
    assert it.category == "single_hop"
    assert it.gold_answer == "Alice"
    assert it.hop_depth == 0
    assert it.gold_entities == ()
    assert it.gold_path == ()
    assert it.gold_sources == ()


def test_full_fixture_all_optional_fields(tmp_path: Path):
    p = _write(
        tmp_path,
        """
- id: q1
  question: "Who owns the auth service?"
  category: multi_hop
  hop_depth: 2
  gold_answer: "Sarah"
  gold_entities:
    - svc-auth
    - person-sarah
  gold_path:
    - svc-auth
    - person-sarah
  gold_sources:
    - doc-123
""",
    )
    items = load_ground_truth(p)
    assert len(items) == 1
    it = items[0]
    assert it.hop_depth == 2
    assert it.gold_entities == (_seed_uuid("svc-auth"), _seed_uuid("person-sarah"))
    assert it.gold_path == (_seed_uuid("svc-auth"), _seed_uuid("person-sarah"))
    assert it.gold_sources == (_seed_uuid("doc-123"),)


def test_unknown_category_raises_valueerror(tmp_path: Path):
    p = _write(
        tmp_path,
        """
- id: q1
  question: "?"
  category: bogus
  gold_answer: "x"
""",
    )
    with pytest.raises(ValueError) as ei:
        load_ground_truth(p)
    assert "bogus" in str(ei.value)


def test_duplicate_id_raises_valueerror(tmp_path: Path):
    p = _write(
        tmp_path,
        """
- id: q1
  question: "a"
  category: single_hop
  gold_answer: "x"
- id: q1
  question: "b"
  category: single_hop
  gold_answer: "y"
""",
    )
    with pytest.raises(ValueError) as ei:
        load_ground_truth(p)
    assert "duplicate" in str(ei.value).lower()
    assert "q1" in str(ei.value)


def test_missing_required_field_raises_valueerror(tmp_path: Path):
    p = _write(
        tmp_path,
        """
- id: q1
  question: "?"
""",
    )
    with pytest.raises(ValueError) as ei:
        load_ground_truth(p)
    assert "category" in str(ei.value)


def test_negative_with_null_gold_answer_ok(tmp_path: Path):
    p = _write(
        tmp_path,
        """
- id: n1
  question: "Unknown stuff?"
  category: negative
  gold_answer: null
""",
    )
    items = load_ground_truth(p)
    assert len(items) == 1
    assert items[0].gold_answer is None
    assert items[0].category == "negative"


def test_negative_with_non_null_gold_answer_raises(tmp_path: Path):
    p = _write(
        tmp_path,
        """
- id: n1
  question: "?"
  category: negative
  gold_answer: "oops"
""",
    )
    with pytest.raises(ValueError) as ei:
        load_ground_truth(p)
    assert "negative" in str(ei.value).lower()


def test_non_negative_with_null_gold_answer_raises(tmp_path: Path):
    p = _write(
        tmp_path,
        """
- id: q1
  question: "?"
  category: single_hop
  gold_answer: null
""",
    )
    with pytest.raises(ValueError) as ei:
        load_ground_truth(p)
    assert "gold_answer" in str(ei.value)


def test_top_level_not_a_list_raises(tmp_path: Path):
    p = _write(
        tmp_path,
        """
id: q1
question: "?"
category: single_hop
gold_answer: "x"
""",
    )
    with pytest.raises(ValueError) as ei:
        load_ground_truth(p)
    assert "list" in str(ei.value).lower()


def test_row_not_a_mapping_raises(tmp_path: Path):
    p = _write(
        tmp_path,
        """
- just-a-string
""",
    )
    with pytest.raises(ValueError) as ei:
        load_ground_truth(p)
    assert "mapping" in str(ei.value).lower()


def test_category_breakdown_returns_all_four_keys(tmp_path: Path):
    items = [
        GroundTruthItem(id="a", question="?", category="single_hop", gold_answer="x"),
        GroundTruthItem(id="b", question="?", category="single_hop", gold_answer="y"),
        GroundTruthItem(id="c", question="?", category="multi_hop", gold_answer="z"),
    ]
    counts = category_breakdown(items)
    assert counts == {
        "single_hop": 2,
        "multi_hop": 1,
        "negative": 0,
        "ambiguous": 0,
    }


def test_is_negative_by_category():
    it = GroundTruthItem(id="n", question="?", category="negative", gold_answer=None)
    assert it.is_negative is True


def test_is_negative_by_null_gold_answer():
    # Dataclass allows constructing this directly (loader forbids it via YAML,
    # but the property contract is "or gold_answer is None"). Pin that contract.
    it = GroundTruthItem(id="a", question="?", category="single_hop", gold_answer=None)
    assert it.is_negative is True


def test_is_negative_false_for_normal():
    it = GroundTruthItem(id="a", question="?", category="single_hop", gold_answer="x")
    assert it.is_negative is False


def test_repo_fixture_has_explicit_hop_depths():
    items = load_ground_truth(Path("tests/eval/fixtures/ground_truth.yaml"))
    assert items
    assert all(isinstance(it.hop_depth, int) for it in items)
    assert all(it.hop_depth >= 0 for it in items)
    assert any(it.hop_depth == 4 for it in items)


def test_repo_fixture_includes_healthcare_domain_items():
    items = load_ground_truth(Path("tests/eval/fixtures/ground_truth.yaml"))
    healthcare = [it for it in items if it.id.startswith("healthcare-")]
    assert len(healthcare) >= 3
    assert {it.hop_depth for it in healthcare} >= {1, 3, 4}
