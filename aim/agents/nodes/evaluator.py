"""Node 6 — Answer Evaluator.

Evaluates the synthesized answer and decides whether a re-search loop is needed.

Three evaluation modes (configured via ``evaluator_mode``):
  - **heuristic** — zero LLM cost, purely metric-based (default)
  - **llm** — uses LLM to assess factual grounding and completeness
  - **hybrid** — runs heuristic first; invokes LLM only when the score is
    in the uncertain zone (between ``evaluator_llm_threshold_low`` and
    ``evaluator_llm_threshold_high``), saving tokens on clearly good or bad answers

Heuristic criteria:
  - citation_coverage: fraction of retrieved sources actually cited in the answer
  - query_coverage: fraction of sub-queries with at least one source
  - confidence: overall_confidence from the synthesizer
  - answer_length: penalises very short answers that are likely incomplete
"""
from __future__ import annotations

import json
import re

import structlog

from aim.agents.state import AgentState
from aim.utils.metrics import EVALUATION_SCORE, RELOOP_TOTAL

log = structlog.get_logger(__name__)

# Weights for each evaluation criterion (sum to 1.0)
_W_CITATION = 0.30
_W_QUERY_COV = 0.30
_W_CONFIDENCE = 0.25
_W_LENGTH = 0.15

# Fallback defaults — overridden by config at runtime.
_RELOOP_THRESHOLD = 0.50
_MAX_LOOPS = 3
_STRUCTURED_GAP_PREFIX = "MULTI_HOP_STRUCTURED_FEEDBACK="


def _parse_missing_hop(hop: str) -> tuple[str, str] | None:
    for separator in ("↔", "â†”", "<->", "->", " to "):
        if separator in hop:
            left, right = hop.split(separator, 1)
            left = left.strip()
            right = right.strip()
            if left and right:
                return left, right
    return None


def _entity_name(entity) -> str:
    name = entity.properties.get("name") if entity.properties else None
    return str(name or entity.entity_id)


def _build_missing_hop_feedback(state: AgentState) -> dict[str, object]:
    entity_names = {
        entity.entity_id: _entity_name(entity)
        for entity in state.graph_entities
    }
    names_by_lower = {
        name.lower(): entity_id
        for entity_id, name in entity_names.items()
    }

    missing: list[dict[str, object]] = []
    for hop in state.missing_hops:
        parsed = _parse_missing_hop(hop)
        if not parsed:
            continue
        left, right = parsed
        left_id = names_by_lower.get(left.lower(), left)
        right_id = names_by_lower.get(right.lower(), right)
        left_neighbors: set[str] = set()
        right_neighbors: set[str] = set()
        for rel in state.graph_relationships:
            if rel.source_id == left_id:
                left_neighbors.add(entity_names.get(rel.target_id, rel.target_id))
            if rel.target_id == left_id:
                left_neighbors.add(entity_names.get(rel.source_id, rel.source_id))
            if rel.source_id == right_id:
                right_neighbors.add(entity_names.get(rel.target_id, rel.target_id))
            if rel.target_id == right_id:
                right_neighbors.add(entity_names.get(rel.source_id, rel.source_id))
        missing.append({
            "source": left,
            "target": right,
            "found_neighbors_of_source": sorted(left_neighbors)[:8],
            "found_neighbors_of_target": sorted(right_neighbors)[:8],
        })

    return {
        "missing": missing,
        "query_intent": state.query_intent,
        "loop_count": state.loop_count,
    }


def _score_citation_coverage(state: AgentState) -> float:
    """Fraction of retrieved sources that the synthesizer actually cited."""
    if not state.sources:
        return 0.0
    cited_ids: set[str] = set()
    for ids in state.citation_map.values():
        cited_ids.update(ids)
    return min(len(cited_ids) / len(state.sources), 1.0)


def _score_query_coverage(state: AgentState) -> float:
    """Fraction of sub-queries that returned at least one source."""
    if not state.sub_queries:
        return 1.0  # no sub-queries → nothing to cover
    covered = sum(
        1 for sq in state.sub_queries
        if state.sub_query_source_map.get(sq)
    )
    return covered / len(state.sub_queries)


def _score_answer_length(state: AgentState) -> float:
    """Penalise very short answers that are likely incomplete."""
    length = len(state.answer)
    if length >= 200:
        return 1.0
    if length >= 100:
        return 0.6
    if length >= 50:
        return 0.3
    return 0.1


def _compute_heuristic_score(state: AgentState) -> tuple[float, float, float, float, float]:
    """Compute the heuristic evaluation score and its components."""
    citation_cov = _score_citation_coverage(state)
    query_cov = _score_query_coverage(state)
    confidence = state.provenance.overall_confidence if state.provenance else 0.0
    length_score = _score_answer_length(state)

    score = (
        _W_CITATION * citation_cov
        + _W_QUERY_COV * query_cov
        + _W_CONFIDENCE * confidence
        + _W_LENGTH * length_score
    )
    return score, citation_cov, query_cov, confidence, length_score


async def _llm_evaluate(state: AgentState) -> tuple[float, str]:
    """Use LLM to assess answer quality — factual grounding, completeness, coherence.

    Returns (normalized_score_0_to_1, feedback_string).
    """
    from aim.llm import get_llm_provider

    source_summary = ", ".join(
        f"{ref.title or ref.uri or sid[:12]}"
        for sid, ref in list(state.sources.items())[:10]
    )

    prompt = (
        "You are an answer quality evaluator. Score the following answer on three criteria:\n"
        "1. Factual Grounding — is every claim supported by the provided sources?\n"
        "2. Completeness — does the answer address all aspects of the question?\n"
        "3. Coherence — is the answer well-structured and logically consistent?\n\n"
        f"**Question:** {state.original_query}\n\n"
        f"**Answer (truncated):** {state.answer[:1500]}\n\n"
        f"**Sources available:** {source_summary}\n\n"
        "Return ONLY a JSON object: {\"score\": <0-10>, \"feedback\": \"<specific gaps>\"}"
    )

    try:
        llm = get_llm_provider()
        response = await llm.invoke(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=256,
        )
        match = re.search(r'\{[^}]+\}', response.content)
        if match:
            parsed = json.loads(match.group())
            raw_score = float(parsed.get("score", 5))
            feedback = str(parsed.get("feedback", ""))
            return round(min(max(raw_score / 10.0, 0.0), 1.0), 4), feedback
    except Exception as exc:
        log.warning("evaluator.llm_error", error=str(exc))

    return 0.5, "LLM evaluation failed — using heuristic fallback."


async def evaluate_answer(state: AgentState) -> AgentState:
    """Evaluate the synthesized answer and decide whether to reloop."""
    from aim.config import get_settings

    settings = get_settings()
    max_loops = settings.max_reasoning_loops
    if state.is_multi_hop:
        max_loops = min(max_loops, 2)
    threshold = settings.reloop_threshold
    mode = settings.evaluator_mode

    # Always compute heuristic score (zero cost)
    heuristic_score, citation_cov, query_cov, confidence, length_score = (
        _compute_heuristic_score(state)
    )

    score = heuristic_score
    llm_feedback = ""

    # LLM evaluation modes
    if mode == "llm":
        # Always use LLM
        llm_score, llm_feedback = await _llm_evaluate(state)
        # Blend: 60% LLM + 40% heuristic
        score = round(0.6 * llm_score + 0.4 * heuristic_score, 4)
    elif mode == "hybrid":
        # Only invoke LLM in the uncertain zone
        low = settings.evaluator_llm_threshold_low
        high = settings.evaluator_llm_threshold_high
        if low < heuristic_score < high:
            llm_score, llm_feedback = await _llm_evaluate(state)
            score = round(0.6 * llm_score + 0.4 * heuristic_score, 4)
            log.info(
                "evaluator.hybrid_llm_invoked",
                heuristic=round(heuristic_score, 3),
                llm=round(llm_score, 3),
                blended=score,
            )

    # Multi-hop penalty: if the graph_searcher detected missing hops, the
    # answer is structurally incomplete even if it reads well. We apply a
    # 15% penalty per missing hop (capped at 0.45 total) to force a reloop.
    hop_penalty = 0.0
    if state.missing_hops and state.is_multi_hop:
        hop_penalty = min(len(state.missing_hops) * 0.15, 0.45)
        score = max(score - hop_penalty, 0.0)
        log.info(
            "evaluator.hop_penalty",
            penalty=round(hop_penalty, 2),
            missing=len(state.missing_hops),
        )

    EVALUATION_SCORE.observe(score)

    log.info(
        "evaluator.scored",
        mode=mode,
        score=round(score, 3),
        citation_cov=round(citation_cov, 2),
        query_cov=round(query_cov, 2),
        confidence=round(confidence, 2),
        length_score=round(length_score, 2),
        hop_penalty=round(hop_penalty, 2),
        loop_count=state.loop_count,
        max_loops=max_loops,
        threshold=threshold,
    )

    # Decide whether to reloop
    needs_reloop = score < threshold and state.loop_count < max_loops
    feedback = ""

    # ── Strategy-aware re-planning ──────────────────────────────────────────
    next_strategy = state.retrieval_strategy
    next_failed = list(state.failed_strategies)

    if needs_reloop:
        RELOOP_TOTAL.inc()
        gaps: list[str] = []
        if citation_cov < 0.3:
            gaps.append("Very few sources were cited - answer may be unsupported.")
        uncovered = [
            sq for sq in state.sub_queries
            if not state.sub_query_source_map.get(sq)
        ]
        if uncovered:
            gaps.append(
                f"Sub-queries with no results: {'; '.join(sq[:80] for sq in uncovered[:3])}"
            )
        if confidence < 0.4:
            gaps.append("Overall retrieval confidence is low.")
        if length_score < 0.5:
            gaps.append("Answer is very short and likely incomplete.")
        if llm_feedback:
            gaps.append(f"LLM evaluation: {llm_feedback}")

        # ── Multi-hop gap closure ─────────────────────────────────────────
        # When the graph_searcher flagged missing_hops (entity pairs with no
        # connecting path), inject them into the feedback so the decomposer
        # generates targeted hop-closing sub-queries on the next loop.
        if state.missing_hops:
            hop_list = "; ".join(state.missing_hops[:5])
            structured = _build_missing_hop_feedback(state)
            gaps.append(
                f"MULTI-HOP GAPS - no graph path found between these pairs: "
                f"{hop_list}. Generate sub-queries that search for the "
                f"intermediate entities connecting them."
            )
            gaps.append(
                _STRUCTURED_GAP_PREFIX
                + json.dumps(structured, ensure_ascii=False, separators=(",", ":"))
            )

        feedback = " | ".join(gaps) if gaps else "Insufficient evidence overall."

        # Determine which modality underperformed and shift strategy
        from aim.schemas.provenance import SourceType
        graph_count = sum(
            1 for ref in state.sources.values()
            if ref.source_type == SourceType.NEO4J_GRAPH
        )
        vector_count = sum(
            1 for ref in state.sources.values()
            if ref.source_type == SourceType.PINECONE_VECTOR
        )

        next_failed.append(state.retrieval_strategy)
        if graph_count < 2 and "vector_heavy" not in next_failed:
            next_strategy = "vector_heavy"
            gaps.append("Strategy shift: graph returned few results -> switching to vector_heavy.")
        elif vector_count < 2 and "graph_heavy" not in next_failed:
            next_strategy = "graph_heavy"
            gaps.append("Strategy shift: vector returned few results -> switching to graph_heavy.")
        elif "exhaustive" not in next_failed:
            next_strategy = "exhaustive"
            gaps.append("Strategy shift: both modalities underperformed -> exhaustive search.")
        feedback = " | ".join(gaps) if gaps else "Insufficient evidence overall."

        log.info("evaluator.reloop", feedback=feedback, strategy=next_strategy)

    return state.model_copy(
        update={
            "evaluation_score": round(score, 4),
            "evaluation_feedback": feedback,
            "needs_reloop": needs_reloop,
            "loop_count": state.loop_count + (1 if needs_reloop else 0),
            "retrieval_strategy": next_strategy,
            "failed_strategies": next_failed,
            "reasoning_steps": [
                *state.reasoning_steps,
                (
                    f"Evaluation ({mode}): score={score:.2f}, "
                    f"strategy={next_strategy} - "
                    f"{'re-searching' if needs_reloop else 'sufficient'}."
                ),
            ],
        }
    )
