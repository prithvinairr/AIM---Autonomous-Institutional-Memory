"""Markdown report renderer for eval results.

Pure function. Takes a results dict (produced by ``harness.run_eval``)
and returns a Markdown string. Kept separate so:

* Report format can be iterated without re-running the eval
  (expensive — hits Neo4j + Pinecone + LLM per item).
* Report logic is trivially unit-testable.
* Multiple renderers (Markdown now; JSON/HTML later if needed) can
  share the same results shape.

Results schema (one key per system under eval):

    {
      "fixture": {"path": "...", "counts": {"single_hop": 25, ...}},
      "systems": {
         "vector_only": {
            "per_item": [{"id": "...", "ndcg": 0.4, "cite": 1.0,
                          "path": 0.0, "reject": 0.0, "likert": 3,
                          "latency_s": 2.1}, ...],
            "by_category": {"single_hop": {"ndcg": 0.42, ...}, ...},
            "overall": {"ndcg": 0.41, "cite": 0.88, "path": 0.12,
                        "reject": 0.33, "likert": 3.2, "latency_s": 2.0},
         },
         "graph_only": {...},
         "aim_full":  {...},
      },
      "exit_criterion": {
         "multi_hop_delta_pp": 17.4,  # aim_full - vector_only, in pp
         "single_hop_delta_pp":  1.2,
         "verdict": "PASS" | "FAIL",
         "rationale": "...",
      }
    }

The exit criterion block is computed by ``harness`` against the target
defined in the customer plan (aim_full beats vector_only on multi-hop
by ≥15pp AND ties/wins single-hop). Renderer just surfaces it.
"""
from __future__ import annotations

from typing import Any

_METRIC_ORDER = ("ndcg", "cite", "path", "reject", "likert", "latency_s")
_METRIC_HEADERS = {
    "ndcg": "NDCG@10",
    "cite": "Citation",
    "path": "Path Acc",
    "reject": "Neg Reject",
    "likert": "Likert",
    "latency_s": "p50 Lat (s)",
}


def render_report(results: dict[str, Any]) -> str:
    """Render the full evaluation report as Markdown.

    Intentionally verbose — this is what lands in the compliance
    dossier and gets handed to prospects. Over-explain the metrics
    inline so nobody has to re-read the plan doc to interpret a row.
    """
    lines: list[str] = []
    lines.append("# AIM Benchmark Report (Phase A.2)")
    lines.append("")
    lines.append(_fixture_section(results.get("fixture", {})))
    lines.append("")
    lines.append(_overall_table(results.get("systems", {})))
    lines.append("")
    lines.append(_by_category_section(results.get("systems", {})))
    lines.append("")
    lines.append(_exit_criterion_section(results.get("exit_criterion", {})))
    lines.append("")
    lines.append(_methodology_note())
    return "\n".join(lines).rstrip() + "\n"


# ── Fixture shape ──────────────────────────────────────────────────────


def _fixture_section(fixture: dict[str, Any]) -> str:
    path = fixture.get("path", "(not provided)")
    counts = fixture.get("counts", {})
    hop_depths = fixture.get("hop_depths", {})
    total = sum(counts.values()) if counts else 0
    rows = ["## Fixture", "", f"- Path: `{path}`", f"- Total items: **{total}**"]
    if counts:
        rows.append("")
        rows.append("| Category | Count |")
        rows.append("|---|---:|")
        for cat in ("single_hop", "multi_hop", "negative", "ambiguous"):
            rows.append(f"| {cat} | {counts.get(cat, 0)} |")
    if hop_depths:
        rows.append("")
        rows.append("| Hop depth | Count |")
        rows.append("|---:|---:|")
        for depth, count in sorted(hop_depths.items(), key=lambda item: int(item[0])):
            rows.append(f"| {depth} | {count} |")
    return "\n".join(rows)


# ── Overall comparison table ───────────────────────────────────────────


def _overall_table(systems: dict[str, Any]) -> str:
    if not systems:
        return "## Overall\n\n_No systems reported._"

    header = ["## Overall", ""]
    cols = [_METRIC_HEADERS[m] for m in _METRIC_ORDER]
    header.append("| System | " + " | ".join(cols) + " |")
    header.append("|---" + "|---:" * len(cols) + "|")

    # Sort for stable diffing: vector_only, graph_only, aim_full, rest.
    preferred = ["vector_only", "graph_only", "aim_full"]
    ordered_names = [n for n in preferred if n in systems] + [
        n for n in systems if n not in preferred
    ]

    for name in ordered_names:
        overall = systems[name].get("overall", {})
        cells = [_fmt(overall.get(m)) for m in _METRIC_ORDER]
        header.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(header)


# ── Per-category breakdown ─────────────────────────────────────────────


def _by_category_section(systems: dict[str, Any]) -> str:
    if not systems:
        return ""
    lines = ["## By category", ""]
    for category in ("single_hop", "multi_hop", "negative", "ambiguous"):
        rows_for_cat = []
        for sys_name, sys_data in systems.items():
            cat_scores = sys_data.get("by_category", {}).get(category)
            if cat_scores:
                rows_for_cat.append((sys_name, cat_scores))
        if not rows_for_cat:
            continue
        lines.append(f"### {category}")
        lines.append("")
        cols = [_METRIC_HEADERS[m] for m in _METRIC_ORDER]
        lines.append("| System | " + " | ".join(cols) + " |")
        lines.append("|---" + "|---:" * len(cols) + "|")
        for name, scores in rows_for_cat:
            cells = [_fmt(scores.get(m)) for m in _METRIC_ORDER]
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines).rstrip()


# ── Exit criterion / PASS-FAIL ─────────────────────────────────────────


def _exit_criterion_section(exit_block: dict[str, Any]) -> str:
    verdict = exit_block.get("verdict", "UNKNOWN")
    rationale = exit_block.get("rationale", "No rationale provided.")
    mh = exit_block.get("multi_hop_delta_pp")
    sh = exit_block.get("single_hop_delta_pp")
    lines = [
        "## Exit criterion (customer plan A.2)",
        "",
        "- Target: `aim_full` beats `vector_only` on multi-hop NDCG by **≥15pp**",
        "  AND ties or wins on single-hop.",
        "",
        f"- Multi-hop Δ (aim_full − vector_only): **{_fmt_pp(mh)}**",
        f"- Single-hop Δ (aim_full − vector_only): **{_fmt_pp(sh)}**",
        "",
        f"**Verdict:** `{verdict}` — {rationale}",
    ]
    return "\n".join(lines)


# ── Methodology disclosure ─────────────────────────────────────────────


def _methodology_note() -> str:
    return (
        "## Methodology notes\n"
        "\n"
        "- **NDCG@10**: binary relevance (retrieved id ∈ gold_entities). Logs the\n"
        "  *right sources were found*; independent of LLM answer quality.\n"
        "- **Citation**: precision — of what the LLM cited, how much matches\n"
        "  `gold_sources`; if an item omits `gold_sources`, the harness falls\n"
        "  back to `gold_entities` so this does not become an abstention score.\n"
        "- **Path accuracy**: length-normalized LCS of retrieved vs gold graph\n"
        "  path. 0.0 for vector-only baseline by definition (no graph path).\n"
        "- **Neg-reject**: keyword check for \"I don't know\" on negative items.\n"
        "  Conservative — false positives are caught by the Likert judge.\n"
        "- **Likert**: 1–5 LLM-judge score on answer fidelity vs `gold_answer`.\n"
        "  Reported as mean; judge prompt in `aim/eval/judge.py`.\n"
        "- **Latency**: wall-clock end-to-end per query, p50 over the fixture.\n"
        "  Measured against the same docker-compose as A.1 — do not compare\n"
        "  across hardware.\n"
    )


# ── Formatting helpers ─────────────────────────────────────────────────


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    if isinstance(v, int):
        return str(v)
    return str(v)


def _fmt_pp(v: Any) -> str:
    """Format a delta value as percentage points with sign."""
    if v is None:
        return "—"
    try:
        return f"{float(v):+.1f}pp"
    except (TypeError, ValueError):
        return str(v)
