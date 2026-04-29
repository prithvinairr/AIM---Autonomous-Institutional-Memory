"""AIM eval harness — Phase A.2 of the customer-ready plan.

Goal: reproducible benchmark numbers so "AIM beats vanilla RAG" stops
being a structural claim and becomes an empirical one.

The module is split into three layers so each is independently testable:

* ``metrics``  — pure functions. Given ground truth + a system's answer
                 + retrieved sources, compute NDCG@10, citation accuracy,
                 multi-hop path accuracy, Likert score. No IO.
* ``loader``   — parses ``ground_truth.yaml`` into typed records. Pure.
* ``report``   — renders a results dict into markdown. Pure.
* ``baselines``— three runners (vector-only, graph-only, AIM full).
                 These ARE IO-bound — they hit Neo4j, Pinecone, the LLM.
                 Kept separate from the pure-function core so the core
                 is unit-testable without a live stack.
* ``harness``  — orchestrator. Loads YAML, runs baselines, calls metrics,
                 renders report. All the glue.
* ``judge``    — LLM-judge for answer-quality Likert. IO-bound.

Exit criterion for A.2 (from aim_customer_and_sota_plan.md): AIM full
must beat vanilla vector RAG on multi-hop accuracy by ≥15 percentage
points, and tie or win on single-hop.
"""
from aim.eval.baselines import (
    Runner,
    SystemResponse,
    make_aim_full_runner,
    make_graph_only_runner,
    make_vector_only_runner,
)
from aim.eval.judge import judge_answer
from aim.eval.loader import GroundTruthItem, category_breakdown, hop_depth_breakdown, load_ground_truth
from aim.eval.metrics import (
    aggregate_by_category,
    citation_accuracy,
    governed_claim_score,
    multi_hop_path_accuracy,
    ndcg_at_k,
    negative_rejection_rate,
)
from aim.eval.report import render_report

__all__ = [
    # loader
    "GroundTruthItem",
    "category_breakdown",
    "hop_depth_breakdown",
    "load_ground_truth",
    # metrics
    "aggregate_by_category",
    "citation_accuracy",
    "governed_claim_score",
    "multi_hop_path_accuracy",
    "ndcg_at_k",
    "negative_rejection_rate",
    # baselines
    "Runner",
    "SystemResponse",
    "make_aim_full_runner",
    "make_graph_only_runner",
    "make_vector_only_runner",
    # judge
    "judge_answer",
    # report
    "render_report",
]
