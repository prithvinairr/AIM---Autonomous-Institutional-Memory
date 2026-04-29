"""Smoke run of the A.2 eval harness with FAKE runners.

Proves the full pipeline works end-to-end without needing Neo4j /
Pinecone / the LLM / live AIM. Emits eval_report_smoke.md.

The fake runners are hand-tuned to produce a *plausible* relative
ordering: aim_full > graph_only > vector_only on multi-hop, roughly
tied on single-hop. These numbers are SIMULATED — not the real
benchmark. Run EVAL.md Step 2 against the live stack for real numbers.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from aim.eval.baselines import SystemResponse
from aim.eval.harness import run_eval_with_exit
from aim.eval.loader import load_ground_truth
from aim.eval.report import render_report

FIXTURE = Path("tests/eval/fixtures/ground_truth.yaml")
OUT = Path("eval_report_smoke.md")


def _plausible_response(
    item, *, recall: float, graph_mode: bool, cite_precision: float
):
    """Build a SystemResponse that simulates a system's behaviour.

    * recall: fraction of gold_entities the runner "retrieves" at top ranks
    * graph_mode: if True, also populate graph_path from gold_path
    * cite_precision: fraction of cited_ids that are in gold_sources
    """
    gold_ents = list(item.gold_entities)
    # Recall: put int(recall * len(gold)) gold hits at ranks 0..n, then noise.
    hits = gold_ents[: int(round(recall * len(gold_ents)))]
    retrieved = tuple(hits + ["noise-1", "noise-2", "noise-3"])

    gold_srcs = list(item.gold_sources)
    if gold_srcs:
        n_hit = int(round(cite_precision * len(gold_srcs)))
        cited = tuple(gold_srcs[:n_hit] + (["bad-cite"] if n_hit < len(gold_srcs) else []))
    else:
        cited = ()

    if graph_mode and item.gold_path:
        gp = list(item.gold_path)
        # Graph path: interleave a detour node, then the gold path.
        path = tuple(["hub-node"] + gp)
    else:
        path = ()

    # Answer string: for negatives, simulate rejection; else a stub.
    if item.is_negative:
        answer = "I don't know — no information in the corpus."
    else:
        answer = f"The answer is {item.gold_answer}."

    return SystemResponse(
        answer=answer,
        retrieved_ids=retrieved,
        cited_ids=cited,
        graph_path=path,
        latency_s=1.0 + (0.5 if graph_mode else 0.0),
    )


def _make_runner(*, recall, graph_mode, cite_precision):
    # Lookup table by id so every runner sees the same item shape.
    items = {it.id: it for it in load_ground_truth(FIXTURE)}

    async def runner(question: str):
        # Cheap id lookup: we know the fixture question matches exactly one item.
        for it in items.values():
            if it.question == question:
                return _plausible_response(
                    it, recall=recall, graph_mode=graph_mode, cite_precision=cite_precision
                )
        return SystemResponse(answer="", error="no matching fixture item")

    return runner


async def main() -> int:
    runners = {
        # Vector-only: decent single-hop recall, poor multi-hop (no graph).
        "vector_only": _make_runner(recall=0.55, graph_mode=False, cite_precision=0.70),
        # Graph-only: strong multi-hop via graph traversal, weak single-hop recall.
        "graph_only":  _make_runner(recall=0.70, graph_mode=True,  cite_precision=0.75),
        # AIM full: best at both thanks to hybrid fusion.
        "aim_full":    _make_runner(recall=0.90, graph_mode=True,  cite_precision=0.92),
    }

    results = await run_eval_with_exit(
        fixture_path=str(FIXTURE),
        runners=runners,
        judge=None,  # skip Likert — no LLM available
    )

    md = render_report(results)
    OUT.write_text(md, encoding="utf-8")

    exit_block = results["exit_criterion"]
    print(f"[smoke] fixture: {FIXTURE} ({sum(results['fixture']['counts'].values())} items)")
    print(f"[smoke] verdict (simulated): {exit_block['verdict']}")
    print(f"[smoke] multi-hop delta (simulated): {exit_block.get('multi_hop_delta_pp')}")
    print(f"[smoke] single-hop delta (simulated): {exit_block.get('single_hop_delta_pp')}")
    print(f"[smoke] report written to: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
