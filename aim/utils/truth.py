"""Claim governance and truth-maintenance helpers."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from aim.schemas.provenance import InstitutionalFact, SourceReference, SourceType

EXCLUSIVE_TARGET_PREDICATES = frozenset({
    "OWNS",
    "MAINTAINS",
    "APPROVED_BY",
    "PROPOSED_BY",
    "MANAGES",
})

_SOURCE_PRIORS = {
    SourceType.JIRA_MCP: 0.88,
    SourceType.NEO4J_GRAPH: 0.84,
    SourceType.PINECONE_VECTOR: 0.62,
    SourceType.SLACK_MCP: 0.52,
    SourceType.LLM_SYNTHESIS: 0.35,
}

_URI_PRIORS = {
    "jira://": 0.90,
    "adr://": 0.92,
    "github://": 0.82,
    "confluence://": 0.78,
    "slack://": 0.52,
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _uri_prior(uri: str | None) -> tuple[float, str]:
    if not uri:
        return 0.50, "unknown"
    lowered = uri.lower()
    for prefix, score in _URI_PRIORS.items():
        if lowered.startswith(prefix):
            return score, prefix.rstrip(":/")
    return 0.55, "linked_artifact"


def _source_prior(fact: InstitutionalFact, sources: dict[str, SourceReference]) -> tuple[float, str]:
    best = _uri_prior(fact.evidence_uri)
    for source_id in fact.support_source_ids:
        ref = sources.get(source_id)
        if not ref:
            continue
        score = _SOURCE_PRIORS.get(ref.source_type, 0.50)
        label = ref.source_type.value
        if score > best[0]:
            best = (score, label)
    return best


def score_fact_authority(
    fact: InstitutionalFact,
    sources: dict[str, SourceReference],
) -> tuple[float, str]:
    """Return an authority score independent of vector similarity alone."""
    prior, label = _source_prior(fact, sources)
    verification_boost = {
        "verified": 0.16,
        "human_verified": 0.18,
        "approved": 0.18,
        "inferred": 0.0,
        "unverified": -0.08,
    }.get(fact.verification_status.lower(), 0.0)
    stale_penalty = -0.25 if fact.stale or fact.truth_status == "stale" else 0.0
    current_bonus = 0.04 if _parse_dt(fact.valid_from) else 0.0
    score = 0.60 * fact.confidence + 0.40 * prior + verification_boost + current_bonus + stale_penalty
    return max(0.0, min(1.0, score)), label


def _groups(facts: Iterable[InstitutionalFact]) -> list[list[InstitutionalFact]]:
    by_subject_predicate: dict[tuple[str, str], list[InstitutionalFact]] = defaultdict(list)
    by_object_predicate: dict[tuple[str, str], list[InstitutionalFact]] = defaultdict(list)
    for fact in facts:
        by_subject_predicate[(fact.subject_entity_id, fact.predicate)].append(fact)
        if fact.predicate in EXCLUSIVE_TARGET_PREDICATES:
            by_object_predicate[(fact.object_entity_id, fact.predicate)].append(fact)

    groups = list(by_subject_predicate.values()) + list(by_object_predicate.values())
    return [
        group for group in groups
        if len({f.object_entity_id for f in group}) > 1
        or len({f.subject_entity_id for f in group}) > 1
    ]


def resolve_truth(
    facts: list[InstitutionalFact],
    sources: dict[str, SourceReference],
) -> list[InstitutionalFact]:
    """Resolve contested facts using authority, verification, and time.

    This does not erase history. Losing claims remain visible as superseded or
    contested, but the current winning claim is explicit and citeable.
    """
    scored: dict[str, InstitutionalFact] = {}
    for fact in facts:
        authority, label = score_fact_authority(fact, sources)
        scored[fact.fact_id] = fact.model_copy(update={
            "authority_score": authority,
            "source_authority": label,
        })

    updates: dict[str, dict[str, object]] = {}
    for group in _groups(scored.values()):
        ordered = sorted(
            group,
            key=lambda f: (
                f.verification_status.lower() in {"verified", "human_verified", "approved"},
                f.authority_score,
                _parse_dt(f.valid_from) or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        winner = ordered[0]
        runner_up = ordered[1] if len(ordered) > 1 else None
        confidence_gap = winner.authority_score - (runner_up.authority_score if runner_up else 0.0)
        ids = [fact.fact_id for fact in group]

        if confidence_gap >= 0.08 or winner.verification_status.lower() in {"verified", "human_verified", "approved"}:
            updates.setdefault(winner.fact_id, {}).update({
                "truth_status": "active",
                "winning_fact_id": winner.fact_id,
                "contradicts_fact_ids": [fid for fid in ids if fid != winner.fact_id],
                "resolution_reason": (
                    f"Selected by {winner.source_authority} authority "
                    f"({winner.authority_score:.2f}) over conflicting claims."
                ),
            })
            for loser in ordered[1:]:
                updates.setdefault(loser.fact_id, {}).update({
                    "truth_status": "superseded",
                    "winning_fact_id": winner.fact_id,
                    "superseded_by_fact_id": winner.fact_id,
                    "contradicts_fact_ids": [fid for fid in ids if fid != loser.fact_id],
                    "resolution_reason": (
                        f"Superseded by {winner.fact_id} from "
                        f"{winner.source_authority} authority."
                    ),
                })
        else:
            for fact in group:
                updates.setdefault(fact.fact_id, {}).update({
                    "truth_status": "contested",
                    "winning_fact_id": None,
                    "contradicts_fact_ids": [fid for fid in ids if fid != fact.fact_id],
                    "resolution_reason": "No authoritative winner; conflicting claims require human adjudication.",
                })

    resolved: list[InstitutionalFact] = []
    for fact_id, fact in scored.items():
        resolved.append(fact.model_copy(update=updates.get(fact_id, {})))

    return sorted(
        resolved,
        key=lambda f: (
            f.truth_status == "active",
            f.truth_status != "superseded",
            f.authority_score,
            f.confidence,
        ),
        reverse=True,
    )
