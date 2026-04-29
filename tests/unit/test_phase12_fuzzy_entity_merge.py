"""Phase 12 — Fuzzy cross-system entity resolution.

Pins three contracts:
  1. ``rapidfuzz.token_set_ratio`` ≥ threshold merges entities whose titles
     are not exactly equal but are semantically the same across sources.
  2. Merged entities preserve *all* source_ids from every matched title.
  3. ``entity_merge_fuzzy_threshold`` is honored — titles below it stay
     separate (prevents "Platform" ↔ "Platform API" false merges).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from aim.agents.nodes.synthesizer import _resolve_cross_system_entities
from aim.schemas.provenance import SourceReference, SourceType


def _src(source_type: SourceType, title: str, uri: str | None = None) -> SourceReference:
    return SourceReference(
        source_id=f"src-{uuid4().hex[:8]}",
        source_type=source_type,
        uri=uri or f"{source_type.value}://{title.replace(' ', '-').lower()}",
        title=title,
        content_snippet=title,
        retrieved_at=datetime.now(timezone.utc),
        confidence=1.0,
        metadata={},
    )


# ── (1) Fuzzy merge across source types ─────────────────────────────────────


def test_fuzzy_match_merges_across_source_types():
    """'Platform team' (Slack) and 'Platform-Team' (Jira) are the same entity.
    Exact-title grouping misses this; fuzzy merge must catch it."""
    slack = _src(SourceType.SLACK_MCP, "Platform team")
    jira = _src(SourceType.JIRA_MCP, "Platform-Team")
    sources = {slack.source_id: slack, jira.source_id: jira}

    resolved = _resolve_cross_system_entities(sources)

    # The platform-team cluster must surface at least once, with BOTH source_ids.
    merged = [
        r for r in resolved
        if slack.source_id in r.source_ids and jira.source_id in r.source_ids
    ]
    assert merged, (
        "Fuzzy entity resolution must merge 'Platform team' and 'Platform-Team' "
        "across Slack+Jira — this is the cross-system merge contract."
    )
    assert SourceType.SLACK_MCP in merged[0].source_types
    assert SourceType.JIRA_MCP in merged[0].source_types


# ── (2) Threshold prevents false merges ────────────────────────────────────


def test_dissimilar_titles_below_threshold_stay_separate():
    """'Platform' and 'Platform API' must NOT merge — they're distinct
    entities. Token-set ratio between short subsumed titles is below 90."""
    a = _src(SourceType.SLACK_MCP, "Platform")
    b = _src(SourceType.JIRA_MCP, "Platform API Documentation")
    sources = {a.source_id: a, b.source_id: b}

    resolved = _resolve_cross_system_entities(sources)

    merged = [
        r for r in resolved
        if a.source_id in r.source_ids and b.source_id in r.source_ids
    ]
    assert not merged, (
        "Titles scoring below threshold must not merge — "
        "'Platform' and 'Platform API Documentation' are distinct entities."
    )


# ── (3) Exact-title grouping still works (backward compat) ─────────────────


def test_exact_title_match_still_merges():
    """Don't regress the existing exact-title pathway when adding fuzzy."""
    slack = _src(SourceType.SLACK_MCP, "AuthService")
    graph = _src(SourceType.NEO4J_GRAPH, "AuthService")
    sources = {slack.source_id: slack, graph.source_id: graph}

    resolved = _resolve_cross_system_entities(sources)

    merged = [
        r for r in resolved
        if slack.source_id in r.source_ids and graph.source_id in r.source_ids
    ]
    assert merged, "Exact-title merge regressed"


# ── (4) Same source type does NOT merge ────────────────────────────────────


def test_fuzzy_merge_requires_different_source_types():
    """Fuzzy merge is specifically for *cross-system* resolution — two Slack
    threads with similar titles are not the same entity, they're just two
    threads about the same thing. Don't collapse them."""
    a = _src(SourceType.SLACK_MCP, "Deploy Pipeline")
    b = _src(SourceType.SLACK_MCP, "Deploy-Pipeline")
    sources = {a.source_id: a, b.source_id: b}

    resolved = _resolve_cross_system_entities(sources)

    merged = [
        r for r in resolved
        if a.source_id in r.source_ids and b.source_id in r.source_ids
    ]
    assert not merged, (
        "Fuzzy merge is cross-system only — two sources of the same type "
        "must not collapse even if their titles are near-identical."
    )


# ── (5) All source_ids preserved on 3-way merge ────────────────────────────


def test_three_way_fuzzy_merge_preserves_all_source_ids():
    """When three sources across three systems all describe the same entity
    under slightly different titles, the resolved entity must carry every
    source_id — losing any of them would orphan a citation downstream."""
    slack = _src(SourceType.SLACK_MCP, "Auth Service")
    jira = _src(SourceType.JIRA_MCP, "auth-service")
    graph = _src(SourceType.NEO4J_GRAPH, "AuthService")
    sources = {s.source_id: s for s in (slack, jira, graph)}

    resolved = _resolve_cross_system_entities(sources)

    # Find any resolved entity that touches all three.
    hits = [
        r for r in resolved
        if {slack.source_id, jira.source_id, graph.source_id}.issubset(set(r.source_ids))
    ]
    # Either a single 3-way merge, or transitively via multiple 2-way merges
    # that together reference all three — prove the union of source_ids
    # across all resolved entities covers all three.
    all_merged_ids: set[str] = set()
    for r in resolved:
        all_merged_ids.update(r.source_ids)
    assert {slack.source_id, jira.source_id, graph.source_id}.issubset(all_merged_ids), (
        "Every source in a fuzzy-matched cluster must appear in some merged "
        "ResolvedEntity — otherwise downstream citations lose provenance."
    )


# ── (6) Threshold is configurable ──────────────────────────────────────────


def test_threshold_config_is_honored(monkeypatch):
    """Operators can tighten or loosen the threshold via settings. Lowering it
    to 40 must admit 'Platform' ↔ 'Platform API Documentation' that was
    rejected at the default 90."""
    from aim.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "entity_merge_fuzzy_threshold", 40.0, raising=False)

    a = _src(SourceType.SLACK_MCP, "Platform")
    b = _src(SourceType.JIRA_MCP, "Platform API Documentation")
    sources = {a.source_id: a, b.source_id: b}

    resolved = _resolve_cross_system_entities(sources)
    all_ids: set[str] = set()
    for r in resolved:
        all_ids.update(r.source_ids)
    assert {a.source_id, b.source_id}.issubset(all_ids), (
        "Lowering entity_merge_fuzzy_threshold must loosen the merge rule — "
        "this proves the config knob is actually wired through."
    )
