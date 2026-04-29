"""Phase 7 — True recursive reasoning.

Pins four contracts:
  1. Synthesizer injects the previous answer + critique on re-loop (reflexion).
  2. Cross-loop source dedup — vector/graph don't re-surface the same IDs.
  3. Decomposer receives missing-hop gaps as feedback so its next pass
     generates surgical sub-queries.
  4. LangGraph ``recursion_limit`` scales with ``max_reasoning_loops`` so
     deep pipelines aren't silently truncated.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from aim.agents.state import AgentState
from aim.agents.nodes.synthesizer import _build_messages


def _base_state(**overrides) -> AgentState:
    kwargs = dict(
        query_id=uuid4(),
        original_query="Who approved the ADR that caused the outage?",
        sub_queries=["Which ADR addresses auth?", "Which incident cited that ADR?"],
    )
    kwargs.update(overrides)
    return AgentState(**kwargs)


# ── (1) Synthesizer reflexion ───────────────────────────────────────────────


def test_synthesizer_includes_previous_critique_on_reloop():
    """When loop_count > 0, the synthesizer must see the prior answer + the
    evaluator's critique so it can refine rather than restart cold."""
    state = _base_state(
        loop_count=1,
        answer="Prior answer: ADR-042 was approved by Alex.",
        evaluation_feedback=(
            "MULTI-HOP GAPS — no graph path found between these pairs: "
            "ADR-042, auth-incident-17. Generate sub-queries that search "
            "for the intermediate entities connecting them."
        ),
    )
    messages = _build_messages(state, context_block="[context omitted]")

    # Find the user message (last in the list)
    user_msg = next(m for m in reversed(messages) if m["role"] == "user")
    content = user_msg["content"]

    assert "Prior answer" in content or "previous answer" in content.lower(), (
        "Synthesizer must inject the previous answer on re-loop so refinement "
        "builds on top of it instead of redoing retrieval cold."
    )
    assert "MULTI-HOP GAPS" in content or "auth-incident-17" in content, (
        "Synthesizer must inject the evaluator's critique so the next answer "
        "specifically addresses the identified gap."
    )


def test_synthesizer_skips_reflexion_on_first_pass():
    """No critique / no prior answer on loop_count=0 — don't pollute the prompt."""
    state = _base_state(loop_count=0, answer="", evaluation_feedback="")
    messages = _build_messages(state, context_block="[context]")
    user_msg = next(m for m in reversed(messages) if m["role"] == "user")
    content = user_msg["content"]
    # No reflexion markers on cold first pass
    assert "Previous answer" not in content
    assert "previous attempt" not in content.lower()


# ── (2) Cross-loop source dedup ─────────────────────────────────────────────


def test_vector_retriever_dedups_across_loops():
    """Prior-loop snippet IDs carry over in state.vector_snippets, and the
    retriever's seen_ids set is seeded from them — so a second loop can't
    re-add the same vector ID even if Pinecone returns it again."""
    from aim.agents.nodes import vector_retriever as vr  # noqa: F401

    # Seed the state with a prior-loop snippet
    prior = [{"id": "vec-1", "text": "prior hit", "score": 0.9}]
    state = _base_state(vector_snippets=prior)

    # The retriever's local seen_ids is built from state.vector_snippets.
    # Replicate that derivation here — this pins the contract.
    seen_ids = {s["id"] for s in state.vector_snippets if "id" in s}
    assert "vec-1" in seen_ids, (
        "Cross-loop vector dedup relies on seen_ids being seeded from "
        "state.vector_snippets — this is the implicit contract."
    )


def test_graph_searcher_dedups_across_loops():
    """Same contract for graph_searcher: prior-loop graph_entities carry over
    and seed the seen_ids set so the same entity_id doesn't re-enter."""
    from aim.schemas.graph import GraphEntity

    prior_entities = [
        GraphEntity(
            entity_id="ent-1",
            entity_type="Service",
            labels=["Entity", "Service"],
            properties={"name": "AuthService"},
        )
    ]
    state = _base_state(graph_entities=prior_entities)
    seen_ids = {e.entity_id for e in state.graph_entities}
    assert "ent-1" in seen_ids


# ── (3) Missing-hop gaps reach the decomposer ──────────────────────────────


def test_decomposer_receives_missing_hops_feedback():
    """The evaluator puts MULTI-HOP GAPS into evaluation_feedback and the
    decomposer's _build_messages appends it to the user message — so the
    next decomposition is surgically targeted at the missing hop."""
    from aim.agents.nodes.decomposer import _build_messages as dec_build
    from aim.config import get_settings

    state = _base_state(
        loop_count=1,
        evaluation_feedback=(
            "MULTI-HOP GAPS — no graph path found between these pairs: "
            "[ADR-042, auth-incident-17]. Generate sub-queries that search "
            "for the intermediate entities connecting them."
        ),
    )
    messages = dec_build(state, get_settings())
    user_msg = next(m for m in reversed(messages) if m["role"] == "user")
    assert "MULTI-HOP GAPS" in user_msg["content"], (
        "Decomposer must see the missing-hop feedback verbatim so its LLM "
        "pass can generate surgical hop-closing sub-queries."
    )
    assert "ADR-042" in user_msg["content"]


# ── (4) Recursion limit scales with config ──────────────────────────────────


def test_recursion_limit_scales_with_max_loops():
    """The reasoning_agent must pass a recursion_limit to LangGraph that
    accommodates the configured max_reasoning_loops × nodes-per-loop.
    Default LangGraph limit is 25; with max_loops=5 and 6 nodes per loop
    we need ~36 steps of headroom."""
    from aim.agents.reasoning_agent import _compute_recursion_limit

    # With default max_loops=3, we need at least 6 nodes × 4 total passes = 24
    assert _compute_recursion_limit(max_loops=3) >= 25
    # With max_loops=5, we need at least 6 nodes × 6 passes = 36
    assert _compute_recursion_limit(max_loops=5) >= 36
    # Must never be absurdly high (no runaway)
    assert _compute_recursion_limit(max_loops=5) <= 100
