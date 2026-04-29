"""Query-conditioned edge & path scoring (Phase 10).

Pre-Phase-10 the graph_searcher ranked paths by a plain mean of
feedback-adjusted ``_REL_TYPE_WEIGHTS``. That's static — two paths with the
same relationship types score identically even when one is obviously more
relevant to the user's query and the other routes through a hub node.

Phase 10 generalises the edge score to a 3-term linear combination:

    edge_score = α·query_affinity + β·feedback_weight + γ·inverse_degree

with ``α + β + γ == 1``. Defaults are ``(0, 1, 0)`` so flag-off the module is
behaviour-equivalent to the current mean-of-feedback path. Callers opt into
query-affinity / degree-dampening by bumping α / γ.

The module is intentionally pure — no Neo4j, no embeddings, no I/O. The
caller is responsible for feeding affinity numbers (e.g. from cosine of the
query embedding against edge-endpoint embeddings) and degree counts (from the
graph client).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Literal


_FLOOR = 0.4  # matches pre-Phase-10 default when no rel_types are known
_TOLERANCE = 1e-6
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "by", "did", "does", "for", "from",
    "how", "is", "it", "of", "on", "or", "that", "the", "to", "was", "what",
    "when", "where", "which", "who", "whom", "why", "with",
}
_TOKEN_ALIASES = {
    "auth": "authentication",
    "authn": "authentication",
    "svc": "service",
    "services": "service",
    "owns": "owner",
    "owned": "owner",
    "lead": "leader",
    "leads": "leader",
    "led": "leader",
    "authored": "author",
    "proposed": "propose",
    "approved": "approve",
    "superseded": "supersede",
    "calls": "call",
    "called": "call",
    "depends": "depend",
    "dependency": "depend",
    "incident": "incident",
    "inc": "incident",
}
_REL_QUERY_HINTS = {
    "OWNS": {"owner", "own", "service"},
    "MANAGES": {"manager", "manage", "leader", "team"},
    "LEADS": {"leader", "lead", "team"},
    "LEADS_PROJECT": {"leader", "lead", "project"},
    "MEMBER_OF": {"member", "team"},
    "PROPOSED_BY": {"author", "propose", "adr"},
    "APPROVED_BY": {"approve", "approved", "adr"},
    "SUPERSEDES": {"supersede", "version", "chain", "current", "previous"},
    "CAUSED_BY": {"cause", "root", "incident"},
    "LED_TO": {"lead", "led", "caused", "accelerated", "followed"},
    "IMPACTED": {"impact", "incident", "service"},
    "RESPONDED_TO": {"respond", "responder", "commander", "incident"},
    "DEPENDS_ON": {"depend", "dependency", "downstream", "upstream", "call"},
    "PART_OF": {"part", "project", "service"},
    "AFFECTS": {"affect", "relate", "service"},
}


@dataclass(frozen=True)
class PathScoringWeights:
    """Linear-combination weights. Must sum to 1 within tolerance."""

    alpha: float = 0.0   # query_affinity weight
    beta: float = 1.0    # feedback_weight (static rel_type prior + learned delta)
    gamma: float = 0.0   # inverse_degree weight (hub dampening)

    def __post_init__(self) -> None:
        total = self.alpha + self.beta + self.gamma
        if abs(total - 1.0) > _TOLERANCE:
            raise ValueError(
                f"PathScoringWeights alpha+beta+gamma must sum to 1.0, got {total:.4f}"
            )
        for name, v in (("alpha", self.alpha), ("beta", self.beta), ("gamma", self.gamma)):
            if v < 0:
                raise ValueError(f"PathScoringWeights {name} must be non-negative")


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _surface_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw in _TOKEN_RE.findall((text or "").lower()):
        if raw in _STOPWORDS:
            continue
        token = _TOKEN_ALIASES.get(raw, raw)
        if len(token) >= 2:
            tokens.add(token)
    return tokens


def path_to_text(path: dict[str, Any]) -> str:
    """Render a path as compact text for query-aware scoring."""
    parts: list[str] = []
    nodes = path.get("path_nodes") or []
    rels = path.get("path_rels") or []
    for i, node in enumerate(nodes):
        name = node.get("name") or node.get("entity_id") or node.get("aim_id") or ""
        labels = " ".join(str(label) for label in (node.get("labels") or []))
        if name or labels:
            parts.append(f"{name} {labels}".strip())
        if i < len(rels):
            parts.append(str(rels[i].get("rel_type", "")).replace("_", " "))
    return " ".join(parts)


def lexical_query_affinity(query: str, path: dict[str, Any]) -> float:
    """Score how directly a graph path answers the query.

    This is deterministic and local: it blends token overlap between the query
    and path text with relationship-type hints such as "approved" ->
    APPROVED_BY and "superseded" -> SUPERSEDES.
    """
    query_tokens = _surface_tokens(query)
    path_tokens = _surface_tokens(path_to_text(path))
    if not query_tokens:
        return 0.0

    overlap = len(query_tokens & path_tokens) / len(query_tokens)
    rel_hint_hits = 0
    rels = path.get("path_rels") or []
    for rel in rels:
        rel_type = str(rel.get("rel_type") or "")
        hints = _REL_QUERY_HINTS.get(rel_type, set())
        if hints & query_tokens:
            rel_hint_hits += 1
    rel_score = rel_hint_hits / max(len(rels), 1)

    nodes = path.get("path_nodes") or []
    endpoint_tokens = set()
    if nodes:
        for node in (nodes[0], nodes[-1]):
            endpoint_tokens.update(
                _surface_tokens(str(node.get("name") or node.get("entity_id") or ""))
            )
    endpoint_score = len(query_tokens & endpoint_tokens) / len(query_tokens)

    return _clamp01((0.55 * overlap) + (0.30 * rel_score) + (0.15 * endpoint_score))


def score_edge(
    *,
    feedback_weight: float,
    query_affinity: float,
    inverse_degree: float,
    weights: PathScoringWeights,
) -> float:
    """Return the weighted edge score, clamped to ``[0, 1]``.

    All three input scalars are expected to live in ``[0, 1]`` already but
    are clamped defensively — a caller passing a raw cosine similarity in
    ``[-1, 1]`` won't blow up downstream.
    """
    score = (
        weights.alpha * query_affinity
        + weights.beta * feedback_weight
        + weights.gamma * inverse_degree
    )
    return _clamp01(score)


def inverse_degree_score(*, src_degree: int, tgt_degree: int) -> float:
    """Map endpoint degrees to a ``[0, 1]`` hub-dampening score.

    Uses ``1 / log2(2 + avg_degree)`` so:
      - avg_degree=1 (rare nodes)  → ≈ 0.63 (normalised to 1.0)
      - avg_degree=20              → ≈ 0.31
      - avg_degree=500             → ≈ 0.11

    Then normalised against the ``avg_degree=1`` ceiling so rare edges score
    ≈ 1.0 — matches the intuition that an edge between two rare nodes is
    high-signal.
    """
    avg = max(0.0, (src_degree + tgt_degree) / 2.0)
    # Guard against negative / NaN: clamp to ≥ 0.
    raw = 1.0 / math.log2(2.0 + avg)
    # Ceiling at avg=0 is 1/log2(2) = 1.0, so raw is already in (0, 1].
    return _clamp01(raw)


def score_path(
    edge_scores: list[float],
    aggregation: Literal["mean", "product"] = "mean",
) -> float:
    """Aggregate per-edge scores into a single path score.

    - ``mean`` — matches the pre-Phase-10 behaviour (robust to long paths).
    - ``product`` — penalises weak links (one bad edge tanks the path).

    An empty list returns ``_FLOOR`` to match the old ``path_score`` default.
    """
    if not edge_scores:
        return _FLOOR
    if aggregation == "mean":
        return _clamp01(sum(edge_scores) / len(edge_scores))
    if aggregation == "product":
        prod = 1.0
        for s in edge_scores:
            prod *= _clamp01(s)
        return _clamp01(prod)
    raise ValueError(f"Unknown aggregation: {aggregation!r}")


def rank_paths(
    paths: list[dict[str, Any]],
    aggregation: Literal["mean", "product"] = "mean",
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Score each path (by its ``edge_scores`` list) and return sorted copies.

    Each returned dict carries a fresh ``path_score`` field. Paths missing an
    ``edge_scores`` key get the documented floor score rather than blowing up
    — real callers ought to populate it, but defensive behaviour keeps the
    graph_searcher pipeline from crashing on malformed inputs.
    """
    scored: list[dict[str, Any]] = []
    for p in paths:
        edges = p.get("edge_scores") or []
        p_out = dict(p)
        p_out["path_score"] = score_path(list(edges), aggregation=aggregation)
        scored.append(p_out)
    scored.sort(key=lambda p: p["path_score"], reverse=True)
    if top_k is not None:
        scored = scored[:top_k]
    return scored


def rerank_paths_for_query(
    query: str,
    paths: list[dict[str, Any]],
    *,
    structural_weight: float = 0.65,
    affinity_weight: float = 0.35,
) -> list[dict[str, Any]]:
    """Return query-aware ranked path copies.

    ``path_score`` remains the structural score. ``path_rerank_score`` is the
    blended score used for ordering and downstream soft boosts.
    """
    if not paths:
        return []
    ranked: list[dict[str, Any]] = []
    for path in paths:
        out = dict(path)
        structural = _clamp01(float(out.get("path_score") or _FLOOR))
        affinity = lexical_query_affinity(query, out)
        out["path_query_affinity"] = round(affinity, 4)
        out["path_rerank_score"] = round(
            _clamp01((structural_weight * structural) + (affinity_weight * affinity)),
            4,
        )
        ranked.append(out)
    ranked.sort(
        key=lambda p: (
            p.get("path_rerank_score", 0.0),
            p.get("path_score", 0.0),
            -int(p.get("hops", 99) or 99),
        ),
        reverse=True,
    )
    return ranked
