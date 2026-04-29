"""A+ upgrade coverage — multi-hop reasoning, causal chains, sovereignty.

Focused tests for the new code paths added to push every hallmark to A+:
- decomposer.is_multi_hop parsing + heuristic backstop
- synthesizer free-text redaction + source classification
- synthesizer sovereignty_audit accumulation
- graph_searcher missing_hops detection + multi-hop pair expansion
- audit_log extended fields
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from aim.agents.nodes.decomposer import decompose_query
from aim.agents.nodes.synthesizer import (
    _classify_source,
    _redact_free_text,
)
from aim.agents.state import AgentState
from aim.llm.base import LLMResponse
from aim.schemas.provenance import SourceReference, SourceType
from aim.schemas.query import ReasoningDepth
from aim.utils.data_classification import reset_classifier


def _make_state(**overrides) -> AgentState:
    defaults = {
        "query_id": uuid4(),
        "original_query": "Who approved the ADR that led to the outage?",
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


def _mock_llm(content: str):
    provider = AsyncMock()
    provider.invoke = AsyncMock(return_value=LLMResponse(
        content=content, input_tokens=10, output_tokens=5, model="test",
    ))
    return provider


# ── Decomposer: is_multi_hop ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_decompose_parses_is_multi_hop_true():
    state = _make_state()
    payload = {
        "sub_queries": ["Which ADR?", "Which incident?", "Who approved?"],
        "intent": "decision",
        "entity_pairs": [["ADR-42", "outage"]],
        "is_multi_hop": True,
    }
    provider = _mock_llm(json.dumps(payload))
    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=provider):
            result = await decompose_query(state)
    assert result.is_multi_hop is True
    assert result.entity_pairs == [["ADR-42", "outage"]]
    assert "multi_hop=True" in result.reasoning_steps[-1]


@pytest.mark.asyncio
async def test_decompose_heuristic_sets_multi_hop_from_entity_pairs():
    """Even if LLM omits is_multi_hop, non-empty entity_pairs forces True."""
    state = _make_state()
    payload = {
        "sub_queries": ["Which ADR?"],
        "intent": "decision",
        "entity_pairs": [["A", "B"]],
    }
    provider = _mock_llm(json.dumps(payload))
    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=provider):
            result = await decompose_query(state)
    assert result.is_multi_hop is True


@pytest.mark.asyncio
async def test_decompose_heuristic_sets_multi_hop_from_causal_markers():
    """3+ sub-queries with causal verbs flip the heuristic backstop."""
    state = _make_state()
    payload = {
        "sub_queries": [
            "Which ADR triggered the outage?",
            "Which incident was caused by that ADR?",
            "Who approved the change?",
        ],
        "intent": "decision",
    }
    provider = _mock_llm(json.dumps(payload))
    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=provider):
            result = await decompose_query(state)
    assert result.is_multi_hop is True


@pytest.mark.asyncio
async def test_decompose_no_heuristic_match_stays_false():
    state = _make_state()
    payload = {"sub_queries": ["What is the auth service?"], "intent": "general"}
    provider = _mock_llm(json.dumps(payload))
    with patch("aim.agents.nodes.decomposer.get_settings", return_value=_mock_settings()):
        with patch("aim.agents.nodes.decomposer.get_llm_provider", return_value=provider):
            result = await decompose_query(state)
    assert result.is_multi_hop is False


# ── Synthesizer free-text redaction ──────────────────────────────────────────


def test_redact_free_text_removes_api_key():
    reset_classifier()
    from aim.utils.data_classification import get_data_classifier
    classifier = get_data_classifier()
    # Pattern: (?:sk|pk|ak|key)[-_][a-zA-Z0-9]{20,}  — no dashes after separator
    text = "Here is sk_abcdefghijABCDEFGHIJ1234567890 used for auth"
    safe, classes, count = _redact_free_text(text, classifier)
    assert "[REDACTED:RESTRICTED]" in safe
    assert count >= 1


def test_redact_free_text_empty_string():
    reset_classifier()
    from aim.utils.data_classification import get_data_classifier
    classifier = get_data_classifier()
    safe, classes, count = _redact_free_text("", classifier)
    assert safe == ""
    assert count == 0
    assert classes == set()


def test_redact_free_text_no_sensitive_content():
    reset_classifier()
    from aim.utils.data_classification import get_data_classifier
    classifier = get_data_classifier()
    safe, classes, count = _redact_free_text("normal documentation text", classifier)
    assert count == 0
    assert "INTERNAL" in classes


# ── Synthesizer _classify_source ─────────────────────────────────────────────


def test_classify_source_graph_type_returns_level():
    reset_classifier()
    from aim.utils.data_classification import get_data_classifier
    ref = SourceReference(
        source_type=SourceType.NEO4J_GRAPH,
        uri="neo4j://node/123",
        title="Test",
        content_snippet="person email: alice@example.com",
        confidence=0.9,
    )
    level = _classify_source(ref, get_data_classifier())
    assert level in ("CONFIDENTIAL", "INTERNAL", "RESTRICTED")


def test_classify_source_vector_type_returns_internal_default():
    reset_classifier()
    from aim.utils.data_classification import get_data_classifier
    ref = SourceReference(
        source_type=SourceType.PINECONE_VECTOR,
        uri="pine://x",
        title="Doc",
        content_snippet="safe public text",
        confidence=0.8,
    )
    level = _classify_source(ref, get_data_classifier())
    assert level == "INTERNAL"


# ── Audit log extended fields ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_log_extended_fields_preserved():
    """New tenant_id, query_excerpt, redaction counts flow through to data_summary."""
    from aim.utils.audit_log import AuditLogger

    logger = AuditLogger()
    fake_redis = AsyncMock()
    fake_redis.setex = AsyncMock()
    fake_redis.zadd = AsyncMock()
    fake_redis.zremrangebyscore = AsyncMock()

    async def get_redis():
        return fake_redis

    with patch.object(logger, "_get_redis", side_effect=get_redis):
        logger._enabled = True
        logger._ttl = 3600
        await logger.log_llm_call(
            query_id="q-1",
            provider="anthropic",
            model="claude",
            num_entities=3,
            num_snippets=2,
            num_mcp_items=1,
            classifications_sent=["INTERNAL"],
            estimated_input_tokens=100,
            tenant_id="tenant-x",
            query_excerpt="why did outage happen?",
            vector_redactions=2,
            mcp_redactions=1,
            field_redactions=4,
            corrective_action="fields=4 vector=2 mcp=1",
        )

    # The call must have stored a JSON payload containing the new fields
    args, kwargs = fake_redis.setex.call_args
    stored = json.loads(args[2])
    ds = stored["data_summary"]
    assert ds["tenant_id"] == "tenant-x"
    assert ds["query_excerpt"].startswith("why did outage")
    assert ds["vector_redactions"] == 2
    assert ds["mcp_redactions"] == 1
    assert ds["field_redactions"] == 4
    assert ds["corrective_action"] == "fields=4 vector=2 mcp=1"


# ── Graph searcher missing_hops & multi-hop pair expansion ──────────────────


@pytest.mark.asyncio
async def test_synthesize_populates_sovereignty_state():
    """End-to-end: synthesize_answer must set source_classifications,
    redacted_fields, and append a sovereignty_audit entry."""
    from aim.agents.nodes.synthesizer import synthesize_answer
    from aim.schemas.graph import GraphEntity

    reset_classifier()

    neo_src = SourceReference(
        source_type=SourceType.NEO4J_GRAPH,
        uri="neo4j://node/alice",
        title="Alice",
        content_snippet="person record",
        confidence=0.9,
        metadata={"entity_id": "alice", "labels": ["Person"]},
    )
    entity = GraphEntity(
        entity_id="alice",
        labels=["Person"],
        properties={"name": "Alice", "email": "alice@example.com", "password": "hunter2"},
        score=0.9,
    )
    state = AgentState(
        query_id=uuid4(),
        original_query="who is alice",
        sub_queries=["who is alice"],
        graph_entities=[entity],
        sources={neo_src.source_id: neo_src},
        sub_query_source_map={"who is alice": [neo_src.source_id]},
        tenant_id="tenant-7",
    )

    llm = AsyncMock()
    llm.invoke = AsyncMock(return_value=LLMResponse(
        content=f"Alice works here. [SRC:{neo_src.source_id}]",
        input_tokens=50,
        output_tokens=20,
        model="test",
    ))
    settings = MagicMock(
        llm_provider="anthropic",
        llm_model="claude",
        llm_temperature=0.1,
        llm_max_tokens=1000,
        encrypted_fields=[],
    )

    with patch("aim.agents.nodes.synthesizer.get_settings", return_value=settings), \
         patch("aim.agents.nodes.synthesizer.get_llm_provider", return_value=llm), \
         patch("aim.agents.nodes.synthesizer.get_audit_logger") as mock_audit:
        mock_audit.return_value.log_llm_call = AsyncMock()
        result = await synthesize_answer(state)

    # password → RESTRICTED, email → CONFIDENTIAL captured in redacted_fields
    assert "alice" in result.redacted_fields
    flagged = result.redacted_fields["alice"]
    assert any("password" in f for f in flagged)
    assert any("email" in f for f in flagged)
    # Per-source classification populated
    assert neo_src.source_id in result.source_classifications
    # Sovereignty audit entry appended
    assert len(result.sovereignty_audit) == 1
    entry = result.sovereignty_audit[0]
    assert entry["tenant_id"] == "tenant-7"
    assert entry["query_excerpt"].startswith("who is alice")
    assert entry["field_redactions"] >= 2
    # Audit log was called with extended fields
    call_kwargs = mock_audit.return_value.log_llm_call.call_args.kwargs
    assert call_kwargs["tenant_id"] == "tenant-7"
    assert call_kwargs["field_redactions"] >= 2


def test_state_carries_multi_hop_and_missing_hops_fields():
    """AgentState has new fields with sensible defaults."""
    state = _make_state()
    assert state.is_multi_hop is False
    assert state.missing_hops == []
    assert state.source_classifications == {}
    assert state.redacted_fields == {}
    assert state.sovereignty_audit == []

    # Mutation via model_copy works
    new_state = state.model_copy(update={
        "is_multi_hop": True,
        "missing_hops": ["A ↔ B"],
        "source_classifications": {"src-1": "INTERNAL"},
    })
    assert new_state.is_multi_hop is True
    assert new_state.missing_hops == ["A ↔ B"]
    assert new_state.source_classifications == {"src-1": "INTERNAL"}


# ── Shared prompts module ────────────────────────────────────────────────────


def test_shared_prompts_exports_graph_schema():
    from aim.agents.prompts import (
        ENTITY_LABELS, RELATIONSHIP_TYPES, GRAPH_SCHEMA_BLOCK,
        INTENT_PROMPTS, MULTIHOP_ADDENDUM,
        RETRIEVED_CONTEXT_OPEN, RETRIEVED_CONTEXT_CLOSE,
    )
    assert "Person" in ENTITY_LABELS
    assert "Service" in ENTITY_LABELS
    assert "causal" in RELATIONSHIP_TYPES
    assert "CAUSED_BY" in GRAPH_SCHEMA_BLOCK
    assert "incident" in INTENT_PROMPTS
    assert "ROOT CAUSE" in INTENT_PROMPTS["incident"]
    assert "MULTI-HOP" in MULTIHOP_ADDENDUM
    assert "<retrieved_context>" in RETRIEVED_CONTEXT_OPEN
    assert "</retrieved_context>" in RETRIEVED_CONTEXT_CLOSE


# ── Prompt injection defense ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_context_block_has_injection_boundary():
    """The context block must wrap all retrieved content in XML boundary tags."""
    from aim.agents.nodes.synthesizer import _build_context_block
    from aim.schemas.graph import GraphEntity

    reset_classifier()
    state = AgentState(
        query_id=uuid4(),
        original_query="test",
        sub_queries=["test"],
        graph_entities=[GraphEntity(
            entity_id="x", labels=["Service"],
            properties={"name": "X"}, score=0.9,
        )],
        sources={},
    )
    block = await _build_context_block(state)
    assert "<retrieved_context>" in block
    assert "</retrieved_context>" in block
    assert "RETRIEVED DATA" in block


# ── Evaluator multi-hop penalty ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluator_applies_hop_penalty():
    """Missing hops on a multi-hop query should penalize the score."""
    from aim.agents.nodes.evaluator import evaluate_answer
    from aim.schemas.provenance import ProvenanceMap

    state = _make_state(
        is_multi_hop=True,
        missing_hops=["A ↔ B", "C ↔ D"],
        sub_queries=["q1"],
        sub_query_source_map={"q1": ["s1"]},
        answer="Some answer " * 30,  # 200+ chars
        citation_map={"claim": ["s1"]},
    )
    # Provide a provenance with decent confidence
    prov = MagicMock(spec=ProvenanceMap)
    prov.overall_confidence = 0.8
    state = state.model_copy(update={"provenance": prov})

    src = SourceReference(
        source_type=SourceType.NEO4J_GRAPH,
        uri="neo4j://node/s1", title="T", content_snippet="s",
        confidence=0.9, metadata={},
    )
    state = state.model_copy(update={"sources": {"s1": src}})

    with patch("aim.config.get_settings") as mock_s:
        mock_s.return_value = MagicMock(
            max_reasoning_loops=2,
            reloop_threshold=0.70,  # above 0.65 so penalized score triggers reloop
            evaluator_mode="heuristic",
            evaluator_llm_threshold_low=0.35,
            evaluator_llm_threshold_high=0.65,
        )
        result = await evaluate_answer(state)

    # 2 missing hops × 0.15 = 0.30 penalty → score = 0.95 − 0.30 = 0.65
    assert result.evaluation_score <= 0.65
    assert result.evaluation_score < 0.95  # strictly lower than unpunished
    # Score 0.65 < threshold 0.70 → reloop triggered → feedback populated
    assert "MULTI-HOP GAPS" in result.evaluation_feedback


# ── Feedback weight loading ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_feedback_weights_returns_base_without_redis():
    """Without Redis, feedback weights fall back to static _REL_TYPE_WEIGHTS."""
    from aim.agents.nodes.graph_searcher import _load_feedback_weights, _REL_TYPE_WEIGHTS
    weights = await _load_feedback_weights()
    assert weights["CAUSED_BY"] == _REL_TYPE_WEIGHTS["CAUSED_BY"]
    assert weights["REFERENCES"] == _REL_TYPE_WEIGHTS["REFERENCES"]


# ── Cache encryption helpers ─────────────────────────────────────────────────


def test_cache_encrypt_decrypt_passthrough_when_disabled():
    """When encryption is disabled, encrypt/decrypt are identity functions."""
    from aim.utils.cache import _encrypt, _decrypt
    data = b'{"hello": "world"}'
    assert _decrypt(_encrypt(data)) == data


def test_cache_encrypt_decrypt_roundtrip_when_enabled():
    """When encryption is enabled with a valid Fernet key, data survives a roundtrip."""
    from cryptography.fernet import Fernet
    from aim.utils.cache import _encrypt, _decrypt, _get_fernet

    key = Fernet.generate_key()
    mock_settings = MagicMock(
        cache_encryption_enabled=True,
        encryption_key=key.decode(),
    )
    with patch("aim.utils.cache.get_settings", create=True):
        # Directly patch _get_fernet to return a real Fernet instance
        with patch("aim.utils.cache._get_fernet", return_value=Fernet(key)):
            plaintext = b'{"secret": "data"}'
            encrypted = _encrypt(plaintext)
            assert encrypted != plaintext  # actually encrypted
            assert _decrypt(encrypted) == plaintext  # roundtrip


def test_cache_decrypt_fallback_on_bad_data():
    """_decrypt returns raw bytes when decryption fails (key mismatch)."""
    from cryptography.fernet import Fernet
    from aim.utils.cache import _decrypt

    # Create a Fernet with a known key, but feed it non-encrypted data
    key = Fernet.generate_key()
    with patch("aim.utils.cache._get_fernet", return_value=Fernet(key)):
        raw = b"not-encrypted-data"
        # Should fall through to the except branch and return raw
        assert _decrypt(raw) == raw


# ── Sovereignty default mode ─────────────────────────────────────────────────


def test_sovereignty_default_mode_is_strict():
    """A+ upgrade: default sovereignty_mode is 'strict' so classified data is
    blocked (or rerouted to local) rather than passively logged."""
    from aim.config import Settings
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        s = Settings(
            anthropic_api_key="sk-test",
            neo4j_password="test",
            pinecone_api_key="test",
            openai_api_key="test",
        )
    assert s.sovereignty_mode == "strict"


def test_sovereignty_strict_mode_reroutes_to_local():
    """In strict mode with fallback_to_local + llm_base_url, allow instead of raise."""
    from aim.utils.sovereignty import SovereigntyGuard, reset_sovereignty_guard
    from aim.utils.data_classification import get_data_classifier

    reset_sovereignty_guard()
    guard = SovereigntyGuard(
        mode="strict",
        allowed_classifications=["public"],
        external_providers=["anthropic"],
    )
    # Patch the classifier on the guard to return a classification that violates policy
    mock_classifier = MagicMock()
    mock_classifier.classify_text.return_value = {"INTERNAL"}  # not in allowed
    guard._classifier = mock_classifier

    mock_settings = MagicMock(
        sovereignty_fallback_to_local=True,
        llm_base_url="http://localhost:11434",
    )
    with patch("aim.config.get_settings", return_value=mock_settings):
        # messages, provider — should NOT raise, rerouted to local
        decision = guard.check(
            messages=[{"content": "some internal data"}],
            provider="anthropic",
        )
        assert decision.allowed is True
        assert "rerouted_to_local" in decision.reason
    reset_sovereignty_guard()


# ── Seed data adversarial content ────────────────────────────────────────────


def test_seed_data_has_adversarial_entities():
    from aim.scripts.seed_demo import ADVERSARIAL, ADVERSARIAL_RELATIONSHIPS
    # Conflicting fact — retracted / superseded statuses
    retracted = [e for e in ADVERSARIAL
                 if str(e.get("properties", {}).get("status", "")) in ("retracted", "superseded")]
    assert len(retracted) >= 2  # runbook v2 + ADR-006 + ADR v1/v2
    # Temporal progression — 3 ADR-001 versions by name
    adr_versions = [e for e in ADVERSARIAL
                    if "ADR-001 v" in str(e.get("properties", {}).get("name", ""))]
    assert len(adr_versions) == 3
    # Noise documents
    noise = [e for e in ADVERSARIAL if "lunch" in str(e.get("properties", {}).get("name", "")).lower()
             or "parking" in str(e.get("properties", {}).get("name", "")).lower()]
    assert len(noise) >= 2
    # Adversarial relationships include SUPERSEDES chain
    supersedes = [r for r in ADVERSARIAL_RELATIONSHIPS if r["rel_type"] == "SUPERSEDES"]
    assert len(supersedes) >= 2


# ── jsonrpc new methods (ping / prompts / subscribe) ─────────────────────────


@pytest.mark.asyncio
async def test_jsonrpc_ping_returns_empty():
    """ping is a no-op keepalive that returns {}."""
    from aim.mcp.jsonrpc import JsonRpcTransport
    d = JsonRpcTransport()
    resp = await d.handle('{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}')
    import json as _json
    data = _json.loads(resp)
    assert data["result"] == {}
    assert data["id"] == 1


@pytest.mark.asyncio
async def test_jsonrpc_prompts_list_returns_empty_list():
    """prompts/list returns {prompts: []} for this stateless server."""
    from aim.mcp.jsonrpc import JsonRpcTransport
    d = JsonRpcTransport()
    resp = await d.handle('{"jsonrpc":"2.0","id":2,"method":"prompts/list","params":{}}')
    import json as _json
    data = _json.loads(resp)
    assert data["result"]["prompts"] == []


@pytest.mark.asyncio
async def test_jsonrpc_prompts_get_returns_error_for_unknown():
    """prompts/get raises not-found for unknown prompt names."""
    from aim.mcp.jsonrpc import JsonRpcTransport
    d = JsonRpcTransport()
    resp = await d.handle('{"jsonrpc":"2.0","id":3,"method":"prompts/get","params":{"name":"nonexistent"}}')
    import json as _json
    data = _json.loads(resp)
    # Should return an error response (internal error wrapping ValueError)
    assert "error" in data


@pytest.mark.asyncio
async def test_jsonrpc_resources_subscribe_acknowledged():
    """resources/subscribe and resources/unsubscribe return {} (stateless ack)."""
    from aim.mcp.jsonrpc import JsonRpcTransport
    d = JsonRpcTransport()
    for method in ("resources/subscribe", "resources/unsubscribe"):
        resp = await d.handle(
            f'{{"jsonrpc":"2.0","id":4,"method":"{method}","params":{{"uri":"file:///test"}}}}'
        )
        import json as _json
        data = _json.loads(resp)
        assert data.get("result") == {}


@pytest.mark.asyncio
async def test_jsonrpc_notifications_initialized_no_response():
    """notifications/initialized is a server-side no-op that returns {}."""
    from aim.mcp.jsonrpc import JsonRpcTransport
    d = JsonRpcTransport()
    resp = await d.handle('{"jsonrpc":"2.0","id":5,"method":"notifications/initialized","params":{}}')
    import json as _json
    data = _json.loads(resp)
    assert data.get("result") == {}


# ── ProvenanceMap helpers ────────────────────────────────────────────────────


def test_provenance_map_with_source_helper():
    """with_source() returns a new ProvenanceMap with the source appended."""
    from aim.schemas.provenance import ProvenanceMap, SourceReference, SourceType
    pmap = ProvenanceMap(query_id=uuid4(), overall_confidence=0.8)
    ref = SourceReference(
        source_type=SourceType.NEO4J_GRAPH,
        title="T",
        content_snippet="c",
        confidence=0.9,
        metadata={},
    )
    updated = pmap.with_source(ref)
    assert ref.source_id in updated.sources
    assert len(updated.sources) == 1


def test_provenance_map_with_graph_node_helper():
    """with_graph_node() returns a new ProvenanceMap with the node appended."""
    from aim.schemas.provenance import ProvenanceMap, GraphProvenanceNode
    pmap = ProvenanceMap(query_id=uuid4(), overall_confidence=0.8)
    node = GraphProvenanceNode(
        entity_id="e1", entity_type="Service", labels=["Service"], properties={}
    )
    updated = pmap.with_graph_node(node)
    assert len(updated.graph_nodes) == 1
    assert updated.graph_nodes[0].entity_id == "e1"


def test_provenance_map_source_types_used():
    """source_types_used property returns set of SourceTypes in sources."""
    from aim.schemas.provenance import ProvenanceMap, SourceReference, SourceType
    ref = SourceReference(
        source_type=SourceType.PINECONE_VECTOR,
        title="V",
        content_snippet="v",
        confidence=0.7,
        metadata={},
    )
    pmap = ProvenanceMap(
        query_id=uuid4(),
        overall_confidence=0.7,
        sources={ref.source_id: ref},
    )
    assert SourceType.PINECONE_VECTOR in pmap.source_types_used


# ── Cache Fernet instance caching ───────────────────────────────────────────


def test_cache_fernet_instance_is_cached():
    """Second call to _get_fernet with same key returns the cached instance."""
    from cryptography.fernet import Fernet
    from aim.utils import cache as cache_mod

    key = Fernet.generate_key().decode()
    # Clear cache state
    cache_mod._fernet_cache.clear()

    mock_settings = MagicMock(cache_encryption_enabled=True, encryption_key=key)
    with patch("aim.config.get_settings", return_value=mock_settings):
        f1 = cache_mod._get_fernet()
        f2 = cache_mod._get_fernet()
        assert f1 is f2  # same instance returned from cache
        assert len(cache_mod._fernet_cache) == 1

    cache_mod._fernet_cache.clear()
