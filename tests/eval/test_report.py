"""Pin tests for aim.eval.report — lock Markdown output substrings.

Substring-based to avoid brittleness on cosmetic whitespace tweaks.
"""
from __future__ import annotations

from aim.eval import render_report


def test_empty_results_renders_without_raising():
    out = render_report({})
    assert "# AIM Benchmark Report" in out


def test_fixture_counts_render():
    results = {
        "fixture": {
            "path": "tests/fixtures/gt.yaml",
            "counts": {"single_hop": 12, "multi_hop": 7, "negative": 3, "ambiguous": 1},
            "hop_depths": {0: 3, 1: 12, 2: 6, 3: 2},
        },
    }
    out = render_report(results)
    assert "## Fixture" in out
    # single_hop count shows up.
    assert "12" in out
    # Total appears (12+7+3+1 = 23).
    assert "23" in out
    assert "Hop depth" in out
    assert "| 3 | 2 |" in out


def test_overall_table_includes_system_names():
    results = {
        "systems": {
            "vector_only": {"overall": {"ndcg": 0.4, "cite": 0.8}},
            "aim_full": {"overall": {"ndcg": 0.6, "cite": 0.9}},
        },
    }
    out = render_report(results)
    assert "## Overall" in out
    assert "vector_only" in out
    assert "aim_full" in out


def test_by_category_section_appears_with_data():
    results = {
        "systems": {
            "aim_full": {
                "overall": {"ndcg": 0.5},
                "by_category": {"multi_hop": {"ndcg": 0.7, "cite": 0.8}},
            },
        },
    }
    out = render_report(results)
    assert "## By category" in out
    assert "### multi_hop" in out


def test_pass_verdict_rationale_appears():
    results = {
        "exit_criterion": {
            "multi_hop_delta_pp": 17.4,
            "single_hop_delta_pp": 1.2,
            "verdict": "PASS",
            "rationale": "AIM full beats vector_only on multi-hop by +17.4pp",
        },
    }
    out = render_report(results)
    assert "PASS" in out
    assert "+17.4pp" in out or "17.4" in out
    assert "AIM full beats vector_only" in out


def test_missing_values_render_as_em_dash():
    results = {
        "systems": {
            "vector_only": {"overall": {"ndcg": None, "cite": None}},
        },
    }
    out = render_report(results)
    assert "—" in out
    assert "None" not in out


def test_system_ordering_preferred_first():
    # Deliberately pass systems in non-preferred order; renderer must
    # emit vector_only, graph_only, aim_full first (in that order).
    results = {
        "systems": {
            "aim_full": {"overall": {"ndcg": 0.6}},
            "custom_xyz": {"overall": {"ndcg": 0.3}},
            "graph_only": {"overall": {"ndcg": 0.5}},
            "vector_only": {"overall": {"ndcg": 0.4}},
        },
    }
    out = render_report(results)
    # Check index order of system names in the Overall table.
    i_vec = out.index("| vector_only |")
    i_graph = out.index("| graph_only |")
    i_aim = out.index("| aim_full |")
    i_custom = out.index("| custom_xyz |")
    assert i_vec < i_graph < i_aim < i_custom
