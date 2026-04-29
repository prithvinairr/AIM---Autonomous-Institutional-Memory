"""Node 1 — Query Decomposer.

Breaks the original user query into N focused sub-queries using Claude.
Each sub-query targets a specific aspect that can be resolved independently
by the graph or vector search nodes.

When conversation history is present, the prior context is injected so the
decomposer generates sub-queries that correctly resolve follow-up references
(e.g. "who else worked on *that*?" becomes specific sub-queries).
"""
from __future__ import annotations

import json
import re

import structlog

from aim.agents.state import AgentState
from aim.config import get_settings
from aim.llm import get_llm_provider
from aim.utils.metrics import CONVERSATION_HISTORY_TOKENS

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are the Query Decomposer for AIM (Autonomous Institutional Memory).
Your job is to break a complex user question into {max_sub_queries} or fewer
focused sub-queries, classify the query intent, and — when the question spans
multiple hops in the knowledge graph — order the sub-queries as a REASONING
CHAIN and name the entity pairs whose relationship must be traced.

Each sub-query must be:
  1. Self-contained and unambiguous.
  2. Answerable via a knowledge graph entity search OR a semantic vector search.
  3. Distinct — no two sub-queries should retrieve the same information.

Multi-hop detection:
- If the question asks about the relationship, chain, or path between entities
  (e.g. "Who approved the ADR that led to the incident that caused the
  runbook?"), produce sub-queries in the ORDER the chain must be resolved:
  anchor → intermediate(s) → terminus — and populate entity_pairs with the
  key endpoints so the graph search can proactively find paths.
- Flag such queries with is_multi_hop = true.

Graph schema (use when generating sub-queries):
  Entity labels: Person, Service, Decision (ADR), Incident, Project, Team,
                 Document/Runbook, Component
  Relationship types:
    OWNS, MANAGES, LEADS, MEMBER_OF, LEADS_PROJECT    — organizational
    DEPENDS_ON, PART_OF, USED_IN, REFERENCES          — structural
    CAUSED_BY, LED_TO, SUPERSEDES, AFFECTS, IMPACTED  — causal / temporal
    PROPOSED_BY, APPROVED_BY                          — decision lineage
    RESPONDED_TO                                      — incident response

If conversation history is provided, use it to resolve pronouns and references
(e.g. "that project", "the person you mentioned", "last time") so every
sub-query is fully self-contained.

Return ONLY valid JSON with this schema:
{{
  "sub_queries": ["query1", "query2"],
  "intent": "general",
  "entity_pairs": [],
  "is_multi_hop": false
}}

intent must be one of: "ownership", "dependency", "incident", "decision", "temporal", "general"
entity_pairs is a list of [entity_a, entity_b] pairs naming the endpoints of
each relationship to trace (e.g. [["Alex", "Auth Service"]]). Leave empty if
the query is not about a relationship.

Example (multi-hop):
{{
  "sub_queries": [
    "Which ADR addresses authentication scaling?",
    "Which incident was caused by that authentication decision?",
    "Which runbook was produced in response to that incident?",
    "Who approved the authentication ADR?"
  ],
  "intent": "decision",
  "entity_pairs": [["authentication ADR", "auth runbook"]],
  "is_multi_hop": true
}}

Example (single-hop):
{{
  "sub_queries": [
    "What teams own the authentication service?",
    "What recent Jira tickets mention auth regressions?"
  ],
  "intent": "ownership",
  "entity_pairs": [],
  "is_multi_hop": false
}}
"""


_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)
_STRUCTURED_GAP_PREFIX = "MULTI_HOP_STRUCTURED_FEEDBACK="


def _extract_json_payload(raw: str) -> str:
    """Return the JSON body from plain JSON or a fenced ```json block."""
    text = raw.strip()
    match = _JSON_FENCE_RE.match(text)
    if match:
        return match.group(1).strip()
    return text


def _extract_structured_gap_feedback(feedback: str) -> dict | None:
    marker_index = (feedback or "").find(_STRUCTURED_GAP_PREFIX)
    if marker_index < 0:
        return None
    payload = feedback[marker_index + len(_STRUCTURED_GAP_PREFIX):].strip()
    try:
        parsed, _end = json.JSONDecoder().raw_decode(payload)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _top_relation_types(intent: str, limit: int = 4) -> list[str]:
    from aim.agents.nodes.graph_searcher import _REL_TYPE_WEIGHTS

    intent_rel_types = {
        "ownership": {"OWNS", "MANAGES", "LEADS", "MEMBER_OF", "LEADS_PROJECT"},
        "dependency": {"DEPENDS_ON", "USED_IN", "PART_OF", "REFERENCES"},
        "incident": {"RESPONDED_TO", "IMPACTED", "CAUSED_BY", "LED_TO"},
        "decision": {"PROPOSED_BY", "APPROVED_BY", "AFFECTS", "SUPERSEDES", "LED_TO"},
        "temporal": {"LED_TO", "CAUSED_BY", "SUPERSEDES"},
    }.get(intent, set(_REL_TYPE_WEIGHTS))
    return sorted(
        intent_rel_types,
        key=lambda rel_type: _REL_TYPE_WEIGHTS.get(rel_type, 0.4),
        reverse=True,
    )[:limit]


def _targeted_gap_subqueries(feedback: str, *, max_sub_queries: int) -> list[str]:
    structured = _extract_structured_gap_feedback(feedback)
    if not structured:
        return []

    rel_text = ", ".join(_top_relation_types(str(structured.get("query_intent") or "general")))
    queries: list[str] = []
    for gap in structured.get("missing", []):
        if not isinstance(gap, dict):
            continue
        source = str(gap.get("source") or "").strip()
        target = str(gap.get("target") or "").strip()
        if not source or not target:
            continue
        queries.append(f"Which entities connect {source} to {target} via {rel_text}?")

        source_neighbors = gap.get("found_neighbors_of_source") or []
        target_neighbors = gap.get("found_neighbors_of_target") or []
        if source_neighbors or target_neighbors:
            left = ", ".join(str(item) for item in source_neighbors[:3])
            right = ", ".join(str(item) for item in target_neighbors[:3])
            queries.append(
                f"What graph path links {source} neighbors ({left or 'known neighbors'}) "
                f"to {target} neighbors ({right or 'known neighbors'})?"
            )
        if len(queries) >= max_sub_queries:
            break
    return queries[:max_sub_queries]


def _build_messages(state: AgentState, settings) -> list[dict[str, str]]:
    """Construct the message list, optionally prepending conversation history."""
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": _SYSTEM_PROMPT.format(
                max_sub_queries=settings.max_sub_queries
            ),
        }
    ]

    # Inject prior turns as clean alternating messages so Claude can resolve
    # references ("that project", "the person you mentioned") without needing
    # artificial "[Prior turn]" prefixes that can confuse the model.
    if state.conversation_history:
        for turn in state.conversation_history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                messages.append({"role": "user", "content": content})
            else:
                # Truncate long assistant turns to keep the context window bounded
                messages.append({"role": "assistant", "content": content[:600]})

    user_content = f"Original query: {state.original_query}"

    # When re-looping after evaluation, inject feedback so the decomposer
    # generates targeted sub-queries that fill the gaps from the first pass.
    if state.evaluation_feedback:
        targeted_queries = _targeted_gap_subqueries(
            state.evaluation_feedback,
            max_sub_queries=settings.max_sub_queries,
        )
        targeted_text = "\n".join(f"- {query}" for query in targeted_queries)
        user_content += (
            f"\n\nIMPORTANT — Previous attempt was insufficient. "
            f"Focus on filling these gaps:\n{state.evaluation_feedback}\n"
            f"Generate refined sub-queries targeting the missing evidence."
        )
        if targeted_text:
            user_content += (
                "\n\nMANDATORY TARGETED MULTI-HOP SUB-QUERIES:\n"
                f"{targeted_text}\n"
                "Preserve these queries exactly unless you can make them more specific."
            )

    # Strategy-aware re-planning: shift the type of sub-queries based on
    # which retrieval modality underperformed in the previous loop.
    strategy = state.retrieval_strategy
    if strategy == "graph_heavy":
        user_content += (
            "\n\nSTRATEGY: graph_heavy — Vector search returned few results. "
            "Generate sub-queries that target SPECIFIC ENTITY NAMES, service names, "
            "person names, decision IDs, and incident IDs. Use exact names from the query."
        )
    elif strategy == "vector_heavy":
        user_content += (
            "\n\nSTRATEGY: vector_heavy — Graph search returned few results. "
            "Generate sub-queries using CONCEPTUAL and SEMANTIC language. Rephrase "
            "with synonyms and broader terms. Describe what you're looking for rather "
            "than using exact names."
        )
    elif strategy == "exhaustive":
        user_content += (
            "\n\nSTRATEGY: exhaustive — Both graph and vector returned few results. "
            "Generate the MAXIMUM number of diverse sub-queries (up to the limit). "
            "Mix exact entity names AND conceptual descriptions. Include broader "
            "context queries and related topics."
        )

    messages.append({"role": "user", "content": user_content})
    return messages


async def decompose_query(state: AgentState) -> AgentState:
    settings = get_settings()
    llm = get_llm_provider()

    messages = _build_messages(state, settings)

    if state.conversation_history:
        CONVERSATION_HISTORY_TOKENS.observe(len(state.conversation_history))

    log.info(
        "decompose_query.start",
        query=state.original_query,
        history_turns=len(state.conversation_history) // 2,
    )

    response = await llm.invoke(messages, temperature=0.0, max_tokens=512)
    raw = response.content.strip()

    input_tokens = response.input_tokens
    output_tokens = response.output_tokens

    sub_queries: list[str] = [state.original_query]
    intent = "general"
    entity_pairs: list[list[str]] = []
    is_multi_hop = False

    try:
        parsed = json.loads(_extract_json_payload(raw))
        if isinstance(parsed, list):
            # Backward-compatible: plain list of strings
            sub_queries = parsed
        elif isinstance(parsed, dict):
            sub_queries = parsed.get("sub_queries", [state.original_query])
            intent = parsed.get("intent", "general")
            entity_pairs = parsed.get("entity_pairs", [])
            is_multi_hop = bool(parsed.get("is_multi_hop", False))
            if not isinstance(sub_queries, list):
                raise ValueError("sub_queries must be a list")
        else:
            raise ValueError("Expected JSON object or array")
    except (json.JSONDecodeError, ValueError):
        log.warning("decompose_query.parse_failed", raw=raw[:200])
        sub_queries = [state.original_query]

    # Heuristic backstop — if the LLM omitted the flag but produced
    # entity_pairs or ≥3 sub-queries with causal connectors, treat as multi-hop.
    if not is_multi_hop:
        if entity_pairs:
            is_multi_hop = True
        elif len(sub_queries) >= 3:
            causal_markers = (
                "caused by", "led to", "resulted in", "approved", "triggered",
                "superseded", "impacted", "resulted from", "after", "because",
                "following", "in response to", "as a result", "which caused",
            )
            joined = " ".join(s.lower() for s in sub_queries if isinstance(s, str))
            if any(m in joined for m in causal_markers):
                is_multi_hop = True

    # Validate intent
    valid_intents = {"ownership", "dependency", "incident", "decision", "temporal", "general"}
    if intent not in valid_intents:
        intent = "general"

    sub_queries = sub_queries[: settings.max_sub_queries]
    targeted_queries = _targeted_gap_subqueries(
        state.evaluation_feedback,
        max_sub_queries=settings.max_sub_queries,
    )
    if targeted_queries:
        sub_queries = list(dict.fromkeys([*targeted_queries, *sub_queries]))[
            : settings.max_sub_queries
        ]
        is_multi_hop = True

    log.info(
        "decompose_query.done",
        count=len(sub_queries),
        intent=intent,
        entity_pairs=entity_pairs[:3],
        is_multi_hop=is_multi_hop,
        sub_queries=sub_queries,
    )

    reasoning_note = (
        f"Decomposed into {len(sub_queries)} sub-queries "
        f"(intent={intent}, multi_hop={is_multi_hop})."
    )

    return state.model_copy(
        update={
            "sub_queries": sub_queries,
            "query_intent": intent,
            "entity_pairs": entity_pairs,
            "is_multi_hop": is_multi_hop,
            "input_tokens": state.input_tokens + input_tokens,
            "output_tokens": state.output_tokens + output_tokens,
            "reasoning_steps": [
                *state.reasoning_steps,
                reasoning_note,
            ],
        }
    )
