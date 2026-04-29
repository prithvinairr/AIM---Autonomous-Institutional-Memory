"""Phase 9 — Adversarial seed data E2E contracts.

Four tests exercising the five hallmarks against deliberately hostile
fixtures from ``tests/fixtures/adversarial_seed``:

  * Sovereignty:    restricted payloads are blocked/rerouted, never sent raw.
  * Causal Lineage: fuzzy entity merge collapses cross-system "Platform team".
  * Causal Lineage: temporal violations increment ``direction_violations``.
  * Multi-Hop:      complete-chain answer beats the decoy on evaluator score.
"""
from __future__ import annotations

import pytest

from tests.fixtures.adversarial_seed import (
    multihop_seed,
    platform_team_variants,
    restricted_payloads,
    time_violation_seed,
)


# ── (1) Sovereignty: restricted data must not reach Anthropic ──────────────


def test_restricted_seed_blocked_from_anthropic(monkeypatch):
    """Every restricted payload must be flagged by the classifier; under
    strict sovereignty the guard blocks Anthropic dispatch (or reroutes).

    This pins the contract that bad data never silently exits the boundary.
    """
    from aim.utils.sovereignty import SovereigntyGuard, SovereigntyViolation
    from aim.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "sovereignty_fallback_to_local", False, raising=False)
    monkeypatch.setattr(s, "llm_base_url", "", raising=False)

    guard = SovereigntyGuard(
        mode="strict",
        allowed_classifications=["PUBLIC", "INTERNAL"],
        external_providers=["anthropic", "openai"],
    )

    leaked_through = []
    for payload in restricted_payloads():
        messages = [{"role": "user", "content": payload}]
        try:
            decision = guard.check(messages, "anthropic")
            # If the guard didn't raise, the only acceptable outcome is a
            # reroute — never a clean "allowed: send to anthropic".
            if decision.allowed and not decision.reason.startswith("rerouted_to_local"):
                leaked_through.append((payload[:60], decision.reason))
        except SovereigntyViolation:
            # Expected — strict mode with no local reroute available.
            continue

    assert not leaked_through, (
        f"Restricted payloads allowed through to anthropic: {leaked_through}"
    )


# ── (2) Fuzzy entity merge resolves "Platform team" cluster ────────────────


def test_fuzzy_entity_merge_resolves_platform_team():
    """All 10 Platform-team variants across Slack/Jira/Graph must collapse
    into one resolved cluster — i.e. every source_id must land in some
    ResolvedEntity that touches at least 2 distinct source_types."""
    from aim.agents.nodes.synthesizer import _resolve_cross_system_entities

    variants = platform_team_variants()
    sources = {v.source_id: v for v in variants}

    resolved = _resolve_cross_system_entities(sources)

    # Collect the source_id → (source_types in its cluster) map.
    covered: dict[str, set] = {}
    for r in resolved:
        if len(set(r.source_types)) < 2:
            continue  # not a cross-system cluster
        for sid in r.source_ids:
            covered.setdefault(sid, set()).update(r.source_types)

    missing = [v.source_id for v in variants if v.source_id not in covered]
    assert not missing, (
        f"Platform-team variants not merged into any cross-system cluster: "
        f"{[next(v.title for v in variants if v.source_id == sid) for sid in missing]}"
    )


# ── (3) Temporal integrity catches inverted causal edges ───────────────────


def test_time_violation_increments_direction_violations():
    """An edge whose declared cause post-dates its effect must be rejected
    and counted as a ``direction_violation`` — not silently inverted."""
    from aim.agents.nodes.synthesizer import _build_temporal_chain
    from aim.agents.state import AgentState
    from uuid import uuid4

    sources, relationships = time_violation_seed()
    state = AgentState(
        query_id=uuid4(),
        original_query="When did the outage happen?",
        sources=sources,
        graph_relationships=relationships,
    )

    _events, direction_violations, _violating_ids = _build_temporal_chain(sources, state)
    assert direction_violations >= 1, (
        "A CAUSED_BY edge with upstream timestamp newer than downstream "
        "must be counted as a direction_violation — otherwise the temporal "
        "chain silently inverts and the UI cannot flag the integrity bug."
    )


# ── (4) Multi-hop beats decoy — evaluator penalty engages ──────────────────


@pytest.mark.asyncio
async def test_multihop_beats_decoy_single_hop():
    """Two answers to the same multi-hop question: one closes every hop,
    the other has a flagged missing hop. The evaluator must score the
    complete chain higher (hop_penalty only applies to the decoy)."""
    from aim.agents.nodes.evaluator import evaluate_answer

    complete, decoy = multihop_seed()

    scored_complete = await evaluate_answer(complete)
    scored_decoy = await evaluate_answer(decoy)

    assert scored_complete.evaluation_score > scored_decoy.evaluation_score, (
        f"Expected complete multi-hop chain to outscore the decoy — "
        f"complete={scored_complete.evaluation_score:.3f} "
        f"decoy={scored_decoy.evaluation_score:.3f}. "
        f"If these are equal, the hop_penalty isn't wiring through."
    )
    # Also: the decoy must trigger a reloop (score below threshold OR
    # missing_hops flagged forces the penalty).
    assert scored_decoy.needs_reloop, (
        "Decoy state has flagged missing_hops and multi-hop penalty — "
        "evaluator must request a reloop."
    )
