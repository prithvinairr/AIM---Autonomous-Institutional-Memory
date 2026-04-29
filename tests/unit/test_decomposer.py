"""Unit tests for the query decomposer node."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from aim.agents.nodes.decomposer import (
    _build_messages,
    _targeted_gap_subqueries,
    decompose_query,
)
from aim.agents.state import AgentState
from aim.llm.base import LLMResponse
from aim.schemas.query import ReasoningDepth


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> AgentState:
    defaults = {
        "query_id": uuid4(),
        "original_query": "Who owns the auth service?",
        "reasoning_depth": ReasoningDepth.STANDARD,
    }
    defaults.update(overrides)
    return AgentState(**defaults)


def _mock_settings(**overrides):
    defaults = {
        "llm_model": "claude-opus-4-6",
        "anthropic_api_key": "sk-test",
        "max_sub_queries": 5,
        "llm_provider": "anthropic",
        "llm_base_url": "",
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _mock_llm_provider(content: str, input_tokens: int = 0, output_tokens: int = 0):
    """Create a mock LLM provider returning a fixed response."""
    provider = AsyncMock()
    provider.invoke = AsyncMock(return_value=LLMResponse(
        content=content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model="test",
    ))
    return provider


# ── _build_messages ──────────────────────────────────────────────────────────


def test_build_messages_without_history():
    state = _make_state()
    settings = _mock_settings()
    msgs = _build_messages(state, settings)
    # System + user (query)
    assert len(msgs) == 2
    assert "Query Decomposer" in msgs[0]["content"]
    assert state.original_query in msgs[1]["content"]


def test_build_messages_with_history():
    state = _make_state(conversation_history=[
        {"role": "user", "content": "Tell me about the auth service"},
        {"role": "assistant", "content": "The auth service is..."},
    ])
    settings = _mock_settings()
    msgs = _build_messages(state, settings)
    # System + 2 history turns + user (query) = 4
    assert len(msgs) == 4
    assert "auth service" in msgs[1]["content"]
    assert "auth service is" in msgs[2]["content"]


def test_build_messages_truncates_long_assistant_turns():
    long_answer = "x" * 2000
    state = _make_state(conversation_history=[
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": long_answer},
    ])
    settings = _mock_settings()
    msgs = _build_messages(state, settings)
    # Assistant turn should be truncated to 600 chars
    assert len(msgs[2]["content"]) == 600


def test_build_messages_max_sub_queries_in_system_prompt():
    settings = _mock_settings(max_sub_queries=3)
    state = _make_state()
    msgs = _build_messages(state, settings)
    assert "3" in msgs[0]["content"]


def test_targeted_gap_subqueries_from_structured_feedback():
    feedback = (
        'MULTI_HOP_STRUCTURED_FEEDBACK={"missing":[{"source":"Auth Service",'
        '"target":"ADR-003","found_neighbors_of_source":["Alex Rivera"],'
        '"found_neighbors_of_target":["JWT migration"]}],"query_intent":"decision"}'
    )

    queries = _targeted_gap_subqueries(feedback, max_sub_queries=3)

    assert queries[0] == (
        "Which entities connect Auth Service to ADR-003 via LED_TO, "
        "SUPERSEDES, APPROVED_BY, PROPOSED_BY?"
    )
    assert "Alex Rivera" in queries[1]


def test_build_messages_marks_structured_gap_queries_as_mandatory():
    feedback = (
        'MULTI_HOP_STRUCTURED_FEEDBACK={"missing":[{"source":"A","target":"B"}],'
        '"query_intent":"incident"}'
    )
    state = _make_state(evaluation_feedback=feedback)
    settings = _mock_settings(max_sub_queries=3)

    user_msg = _build_messages(state, settings)[-1]["content"]

    assert "MANDATORY TARGETED MULTI-HOP SUB-QUERIES" in user_msg
    assert "Which entities connect A to B via" in user_msg


# ── decompose_query ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_decompose_returns_valid_sub_queries():
    state = _make_state()
    sub_queries = ["Who owns auth?", "What is the architecture?"]

    mock_provider = _mock_llm_provider(
        content=json.dumps(sub_queries),
        input_tokens=100,
        output_tokens=50,
    )

    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=mock_provider):
            result = await decompose_query(state)

    assert result.sub_queries == sub_queries
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert "Decomposed into 2 sub-queries" in result.reasoning_steps[-1]


@pytest.mark.asyncio
async def test_decompose_falls_back_on_invalid_json():
    state = _make_state()

    mock_provider = _mock_llm_provider(content="This is not valid JSON")

    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=mock_provider):
            result = await decompose_query(state)

    # Fallback: entire query becomes single sub-query
    assert result.sub_queries == [state.original_query]


@pytest.mark.asyncio
async def test_decompose_accepts_fenced_json_object():
    state = _make_state()

    mock_provider = _mock_llm_provider(
        content="""```json
{
  "sub_queries": ["Find the auth owner", "Find the ADR they authored"],
  "intent": "decision",
  "entity_pairs": [["auth service", "ADR"]],
  "is_multi_hop": true
}
```""",
        input_tokens=10,
        output_tokens=8,
    )

    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=mock_provider):
            result = await decompose_query(state)

    assert result.sub_queries == ["Find the auth owner", "Find the ADR they authored"]
    assert result.query_intent == "decision"
    assert result.entity_pairs == [["auth service", "ADR"]]
    assert result.is_multi_hop is True


@pytest.mark.asyncio
async def test_decompose_truncates_to_max_sub_queries():
    state = _make_state()
    many_queries = [f"Sub-query {i}" for i in range(10)]

    mock_provider = _mock_llm_provider(
        content=json.dumps(many_queries),
        input_tokens=50,
        output_tokens=30,
    )

    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings(max_sub_queries=3)):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=mock_provider):
            result = await decompose_query(state)

    assert len(result.sub_queries) == 3


@pytest.mark.asyncio
async def test_decompose_accumulates_tokens():
    state = _make_state(input_tokens=200, output_tokens=100)

    mock_provider = _mock_llm_provider(
        content=json.dumps(["sub-q"]),
        input_tokens=50,
        output_tokens=25,
    )

    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=mock_provider):
            result = await decompose_query(state)

    assert result.input_tokens == 250
    assert result.output_tokens == 125


@pytest.mark.asyncio
async def test_decompose_non_array_json_falls_back():
    """If LLM returns valid JSON that isn't an array, fall back to original query."""
    state = _make_state()

    mock_provider = _mock_llm_provider(
        content=json.dumps({"query": "not an array"}),
    )

    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=mock_provider):
            result = await decompose_query(state)

    assert result.sub_queries == [state.original_query]


# ── Coverage: intent defaults to "general" when missing (line 86) ──────────


@pytest.mark.asyncio
async def test_decompose_intent_defaults_to_general_when_missing():
    """When the parsed JSON dict has no 'intent' key, intent defaults to 'general'."""
    state = _make_state()

    mock_provider = _mock_llm_provider(
        content=json.dumps({"sub_queries": ["Who owns auth?"], "entity_pairs": []}),
        input_tokens=10,
        output_tokens=5,
    )

    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=mock_provider):
            result = await decompose_query(state)

    assert result.query_intent == "general"
    assert result.sub_queries == ["Who owns auth?"]


# ── Coverage: CONVERSATION_HISTORY_TOKENS observation (line 103) ────────────


@pytest.mark.asyncio
async def test_decompose_observes_conversation_history_tokens():
    """When conversation_history is present, CONVERSATION_HISTORY_TOKENS histogram is observed."""
    state = _make_state(conversation_history=[
        {"role": "user", "content": "Tell me about auth"},
        {"role": "assistant", "content": "Auth is..."},
    ])

    mock_provider = _mock_llm_provider(
        content=json.dumps(["Follow up on auth"]),
    )

    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=mock_provider):
            with patch("aim.agents.nodes.decomposer.CONVERSATION_HISTORY_TOKENS") as mock_histogram:
                result = await decompose_query(state)

    mock_histogram.observe.assert_called_once_with(2)


# ── Coverage: sub_queries type validation — not a list (lines 131-133) ──────


@pytest.mark.asyncio
async def test_decompose_sub_queries_not_list_falls_back():
    """When sub_queries in parsed JSON is not a list, ValueError triggers fallback."""
    state = _make_state()

    mock_provider = _mock_llm_provider(
        content=json.dumps({"sub_queries": "not a list", "intent": "ownership"}),
    )

    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=mock_provider):
            result = await decompose_query(state)

    # Falls back to original query
    assert result.sub_queries == [state.original_query]


# ── Coverage: invalid intent defaults to "general" (line 141) ──────────────


@pytest.mark.asyncio
async def test_decompose_invalid_intent_defaults_to_general():
    """When intent is not in the valid set, it defaults to 'general'."""
    state = _make_state()

    mock_provider = _mock_llm_provider(
        content=json.dumps({
            "sub_queries": ["What is the auth service?"],
            "intent": "banana",
        }),
        input_tokens=10,
        output_tokens=5,
    )

    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=mock_provider):
            result = await decompose_query(state)

    assert result.query_intent == "general"
    assert result.sub_queries == ["What is the auth service?"]
