"""Adversarial seed data for Phase 9 — stress-tests the 5 hallmarks.

Five categories of deliberately hostile fixtures:

1. ``restricted_payloads`` — 10 free-text blobs carrying PII/secrets that
   ``DataClassifier.classify_text`` must label RESTRICTED (SSN, API keys,
   private keys, GitHub PATs, Slack tokens, etc.).  Sovereignty probes.

2. ``platform_team_variants`` — 10 SourceReference objects describing "the
   Platform team" across Slack/Jira/Graph in subtly different casings
   ("Platform team", "platform-team", "Platform Team", "PlatformTeam"…).
   Fuzzy-merge probes.

3. ``time_violation_seed`` — pair of sources + CAUSED_BY edge whose
   timestamps contradict the declared causal direction (effect's cause is
   newer than the effect itself).  Temporal-integrity probes.

4. ``multihop_seed`` — two AgentState shapes: ``complete`` (all hops closed)
   vs ``decoy`` (missing hop flagged).  Evaluator must score the complete
   chain higher and force the decoy to re-loop.

Usage::

    from tests.fixtures.adversarial_seed import (
        restricted_payloads,
        platform_team_variants,
        time_violation_seed,
        multihop_seed,
    )
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from aim.schemas.graph import GraphRelationship
from aim.schemas.provenance import SourceReference, SourceType


# ── (1) Sovereignty probes ──────────────────────────────────────────────────


def restricted_payloads() -> list[str]:
    """Ten free-text blobs that MUST classify as RESTRICTED.

    Each hits a distinct value-based pattern in
    ``_RESTRICTED_VALUE_PATTERNS``.  Mixed into realistic Slack/Jira-style
    context so the detector can't rely on clean isolation.
    """
    return [
        # 1-2: SSNs embedded in HR conversations
        "Alex mentioned his SSN 123-45-6789 in the onboarding DM — please scrub.",
        "Jira ticket body: 'new hire SSN on file is 987-65-4321 per HR portal'.",
        # 3-4: API keys in incident threads
        "sk-prod-" + "abc123def456ghi789jkl012mno345 was rotated at 14:02 UTC.",
        "Found leaked key ak_live_9876543210fedcba9876543210fedcba in repo history.",
        # 5: Private key header in paste
        "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...",
        # 6-7: GitHub PATs
        "rotate token ghp_" + "abcdef1234567890ABCDEF1234567890abcdef — expiring tonight.",
        "CI broke because ghp_" + "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ was revoked.",
        # 8-9: Slack tokens
        "xoxb-" + "1234567890-ABCDEFGHIJ is the bot token — do not paste in public.",
        "posted xoxp-USER-TOKEN-HERE in #general by mistake, deleted within 30s.",
        # 10: Nested — SSN inside otherwise benign jira body
        "[JIRA PLAT-901] User reported 'my SSN 555-44-3333 shows up in logs'.",
    ]


# ── (2) Fuzzy entity-merge probes ──────────────────────────────────────────


def _src(source_type: SourceType, title: str) -> SourceReference:
    return SourceReference(
        source_id=f"src-{uuid4().hex[:8]}",
        source_type=source_type,
        uri=f"{source_type.value}://{title.replace(' ', '-').lower()}",
        title=title,
        content_snippet=f"Discussion about {title}",
        retrieved_at=datetime.now(timezone.utc),
        confidence=1.0,
        metadata={},
    )


def platform_team_variants() -> list[SourceReference]:
    """Ten sources describing 'Platform team' across systems in messy casings."""
    return [
        _src(SourceType.SLACK_MCP, "Platform team"),
        _src(SourceType.JIRA_MCP,  "Platform-Team"),
        _src(SourceType.NEO4J_GRAPH, "PlatformTeam"),
        _src(SourceType.SLACK_MCP, "platform team"),
        _src(SourceType.JIRA_MCP,  "Platform Team"),
        _src(SourceType.NEO4J_GRAPH, "Platform  Team"),  # double space
        _src(SourceType.SLACK_MCP, "the Platform team"),
        _src(SourceType.JIRA_MCP,  "Platform_Team"),
        _src(SourceType.NEO4J_GRAPH, "platform-team"),
        _src(SourceType.SLACK_MCP, "Platform team "),  # trailing space
    ]


# ── (3) Temporal-integrity probes ──────────────────────────────────────────


def time_violation_seed() -> tuple[dict[str, SourceReference], list[GraphRelationship]]:
    """Two sources whose CAUSED_BY edge is a temporal lie:
    the declared upstream cause has a *newer* timestamp than the downstream
    effect.  _build_temporal_chain must flag this as a direction_violation."""
    now = datetime.now(timezone.utc)
    # Effect timestamped BEFORE its declared cause — impossible.
    effect = SourceReference(
        source_id="src-effect-1",
        source_type=SourceType.NEO4J_GRAPH,
        uri="graph://entity/effect",
        title="Outage of payments service",
        content_snippet="payments down 2m",
        retrieved_at=now - timedelta(hours=2),
        confidence=1.0,
        metadata={
            "entity_id": "ent-effect",
            "created_at": (now - timedelta(hours=2)).isoformat(),
        },
    )
    cause = SourceReference(
        source_id="src-cause-1",
        source_type=SourceType.NEO4J_GRAPH,
        uri="graph://entity/cause",
        title="Deploy of buggy migration",
        content_snippet="migration rolled out",
        retrieved_at=now,
        confidence=1.0,
        metadata={
            "entity_id": "ent-cause",
            "created_at": now.isoformat(),  # later than the effect
        },
    )
    rel = GraphRelationship(
        rel_id="rel-violation-1",
        rel_type="CAUSED_BY",
        source_id="ent-effect",
        target_id="ent-cause",  # effect CAUSED_BY cause → cause upstream of effect
    )
    return (
        {effect.source_id: effect, cause.source_id: cause},
        [rel],
    )


# ── (4) Multi-hop probes ────────────────────────────────────────────────────


def multihop_seed():
    """Two state shapes for the same multi-hop question:

    * ``complete``: all hops closed — missing_hops=[].
    * ``decoy``:    evidence that *looks* relevant but leaves a hop open.

    Both claim ``is_multi_hop=True`` so the evaluator's 15%/hop penalty
    actually engages on the decoy.
    """
    from uuid import uuid4 as _uuid
    from aim.agents.state import AgentState

    shared_kwargs = dict(
        original_query="Who approved the ADR that caused the outage?",
        sub_queries=[
            "Which ADR addresses payment auth?",
            "Which incident cited that ADR?",
        ],
        answer=(
            "ADR-042 was approved by Alex Chen on 2026-02-14 [SRC:s1]. "
            "The payment outage on 2026-03-01 cited ADR-042 as the root "
            "cause in its postmortem [SRC:s2]."
        ),
        is_multi_hop=True,
        entity_pairs=[("ADR-042", "incident-17")],
    )

    complete = AgentState(
        query_id=_uuid(),
        missing_hops=[],
        **shared_kwargs,
    )
    decoy = AgentState(
        query_id=_uuid(),
        missing_hops=["ADR-042 -> incident-17"],
        **shared_kwargs,
    )
    return complete, decoy
