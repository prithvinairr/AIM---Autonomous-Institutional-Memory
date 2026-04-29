"""Tests for Phase 3 — Semantic Fusion, Multi-tenancy, Field-level Encryption."""
from __future__ import annotations

import hashlib
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ── 1. Semantic Cross-Modal Fusion ───────────────────────────────────────────

class TestSemanticTitleSimilarity:
    """Tests for _semantic_title_similarity in synthesizer."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from aim.agents.nodes.synthesizer import _semantic_title_similarity
        self.sim = _semantic_title_similarity

    def test_identical_strings(self):
        assert self.sim("Payment Service", "Payment Service") == 1.0

    def test_case_insensitive(self):
        assert self.sim("Payment Service", "payment service") == 1.0

    def test_empty_strings(self):
        assert self.sim("", "something") == 0.0
        assert self.sim("something", "") == 0.0
        assert self.sim("", "") == 0.0

    def test_substring_match(self):
        score = self.sim("Payment", "Payment Service Overview")
        assert score >= 0.90  # substring → 0.95

    def test_reverse_substring_match(self):
        score = self.sim("Payment Service Overview", "Payment")
        assert score >= 0.90

    def test_high_overlap_tokens(self):
        score = self.sim("incident response runbook", "incident response guide")
        assert score >= 0.75

    def test_completely_different(self):
        score = self.sim("alpha beta gamma", "xylophone zebra quilt")
        assert score < 0.5

    def test_prefix_boost(self):
        """Words sharing a prefix should get a boost."""
        score_with_prefix = self.sim("deploy deployment", "deploy config")
        score_without = self.sim("release ship", "deploy config")
        assert score_with_prefix > score_without

    def test_single_word_exact(self):
        assert self.sim("auth", "auth") == 1.0

    def test_fuzzy_near_miss(self):
        """Slight typo should still produce reasonable similarity."""
        score = self.sim("authentication service", "authenticaiton service")
        assert score >= 0.85


# ── 2. Multi-tenancy ────────────────────────────────────────────────────────

class TestMultiTenancyConfig:
    """Verify config.multi_tenant and tenant_id plumbing."""

    def test_default_multi_tenant_false(self):
        """multi_tenant defaults to False."""
        from aim.config import Settings

        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "test",
            "NEO4J_PASSWORD": "test",
            "PINECONE_API_KEY": "test",
            "OPENAI_API_KEY": "test",
        }):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                s = Settings()
        assert s.multi_tenant is False

    def test_multi_tenant_enabled(self):
        from aim.config import Settings

        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "test",
            "NEO4J_PASSWORD": "test",
            "PINECONE_API_KEY": "test",
            "OPENAI_API_KEY": "test",
            "MULTI_TENANT": "true",
        }):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                s = Settings()
        assert s.multi_tenant is True


class TestAgentStateTenantId:
    """Verify tenant_id field in AgentState."""

    def test_default_empty(self):
        from aim.agents.state import AgentState
        state = AgentState(query_id=uuid4(), original_query="test")
        assert state.tenant_id == ""

    def test_custom_tenant_id(self):
        from aim.agents.state import AgentState
        state = AgentState(
            query_id=uuid4(),
            original_query="test",
            tenant_id="abc123",
        )
        assert state.tenant_id == "abc123"


class TestTenantCypherQueries:
    """Verify tenant-scoped Cypher query variants."""

    def test_tenant_search_has_where_clause(self):
        from aim.graph.queries import ENTITY_FULLTEXT_SEARCH_TENANT
        assert "WHERE node.tenant_id = $tenant_id" in ENTITY_FULLTEXT_SEARCH_TENANT

    def test_tenant_upsert_sets_tenant(self):
        from aim.graph.queries import UPSERT_ENTITY_TENANT
        assert "SET n.tenant_id = $tenant_id" in UPSERT_ENTITY_TENANT

    def test_base_search_no_tenant_filter(self):
        from aim.graph.queries import ENTITY_FULLTEXT_SEARCH
        assert "tenant_id" not in ENTITY_FULLTEXT_SEARCH

    def test_base_upsert_no_tenant(self):
        from aim.graph.queries import UPSERT_ENTITY
        assert "tenant_id" not in UPSERT_ENTITY


class TestGraphSearcherTenantPassthrough:
    """Verify graph_searcher passes tenant_id to Neo4j client calls."""

    @pytest.fixture
    def _state(self):
        from aim.agents.state import AgentState
        return AgentState(
            query_id=uuid4(),
            original_query="test query",
            sub_queries=["sub q1"],
            tenant_id="tenant_xyz",
        )

    @pytest.mark.asyncio
    async def test_search_filtered_receives_tenant_id(self, _state):
        """search_filtered should be called with tenant_id from state."""
        from aim.schemas.graph import GraphSearchResult

        mock_result = GraphSearchResult(entities=[], relationships=[], total_traversed=0)

        with patch("aim.agents.nodes.graph_searcher.Neo4jClient") as MockClient, \
             patch("aim.agents.nodes.graph_searcher.get_breaker") as mock_breaker:
            client_inst = MockClient.return_value
            client_inst.close = AsyncMock()

            breaker_inst = MagicMock()
            breaker_inst.call = AsyncMock(return_value=mock_result)
            mock_breaker.return_value = breaker_inst

            from aim.agents.nodes.graph_searcher import search_knowledge_graph
            await search_knowledge_graph(_state)

            # Verify search_filtered was called with tenant_id
            call_kwargs = breaker_inst.call.call_args
            assert call_kwargs is not None
            # The call is breaker.call(client.search_filtered, ..., tenant_id=...)
            _, kwargs = call_kwargs
            assert kwargs.get("tenant_id") == "tenant_xyz"


class TestReasoningAgentTenantId:
    """Verify run_reasoning_agent accepts and passes tenant_id."""

    def test_signature_has_tenant_id(self):
        import inspect
        from aim.agents.reasoning_agent import run_reasoning_agent
        sig = inspect.signature(run_reasoning_agent)
        assert "tenant_id" in sig.parameters
        assert sig.parameters["tenant_id"].default == ""

    def test_stream_signature_has_tenant_id(self):
        import inspect
        from aim.agents.reasoning_agent import stream_reasoning_agent
        sig = inspect.signature(stream_reasoning_agent)
        assert "tenant_id" in sig.parameters
        assert sig.parameters["tenant_id"].default == ""


# ── 3. Field-level Encryption ───────────────────────────────────────────────

class TestEncryptionNoKey:
    """When no encryption key is set, encrypt/decrypt are no-ops."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        from aim.utils.encryption import reset_encryption
        reset_encryption()
        yield
        reset_encryption()

    def test_encrypt_value_noop(self):
        with patch("aim.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(encryption_key="", encrypted_fields=[])
            from aim.utils.encryption import encrypt_value, reset_encryption
            reset_encryption()
            result = encrypt_value("secret_data")
            assert result == "secret_data"

    def test_decrypt_value_noop(self):
        with patch("aim.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(encryption_key="", encrypted_fields=[])
            from aim.utils.encryption import decrypt_value, reset_encryption
            reset_encryption()
            result = decrypt_value("secret_data")
            assert result == "secret_data"

    def test_encrypt_fields_noop(self):
        with patch("aim.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(encryption_key="", encrypted_fields=[])
            from aim.utils.encryption import encrypt_fields, reset_encryption
            reset_encryption()
            props = {"name": "Alice", "email": "alice@test.com"}
            result = encrypt_fields(props, ["email"])
            assert result == props

    def test_decrypt_fields_noop(self):
        with patch("aim.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(encryption_key="", encrypted_fields=[])
            from aim.utils.encryption import decrypt_fields, reset_encryption
            reset_encryption()
            props = {"name": "Alice", "email": "alice@test.com"}
            result = decrypt_fields(props, ["email"])
            assert result == props


class TestEncryptionWithKey:
    """Roundtrip encryption with a real Fernet key."""

    @pytest.fixture(autouse=True)
    def _setup_key(self):
        from aim.utils.encryption import reset_encryption
        reset_encryption()
        try:
            from cryptography.fernet import Fernet
            self.key = Fernet.generate_key().decode()
        except ImportError:
            pytest.skip("cryptography package not installed")
        yield
        reset_encryption()

    def test_encrypt_decrypt_roundtrip(self):
        with patch("aim.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                encryption_key=self.key,
                encrypted_fields=["email"],
            )
            from aim.utils.encryption import encrypt_value, decrypt_value, reset_encryption
            reset_encryption()

            plaintext = "alice@example.com"
            encrypted = encrypt_value(plaintext)
            assert encrypted != plaintext  # must be different
            decrypted = decrypt_value(encrypted)
            assert decrypted == plaintext

    def test_encrypt_fields_selective(self):
        with patch("aim.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                encryption_key=self.key,
                encrypted_fields=["email", "ssn"],
            )
            from aim.utils.encryption import encrypt_fields, decrypt_fields, reset_encryption
            reset_encryption()

            props = {
                "name": "Alice",
                "email": "alice@example.com",
                "ssn": "123-45-6789",
                "age": 30,  # non-string, should be left alone
            }
            encrypted = encrypt_fields(props, ["email", "ssn"])

            # name and age unchanged
            assert encrypted["name"] == "Alice"
            assert encrypted["age"] == 30

            # email and ssn encrypted
            assert encrypted["email"] != "alice@example.com"
            assert encrypted["ssn"] != "123-45-6789"

            # Roundtrip
            decrypted = decrypt_fields(encrypted, ["email", "ssn"])
            assert decrypted["email"] == "alice@example.com"
            assert decrypted["ssn"] == "123-45-6789"
            assert decrypted["name"] == "Alice"
            assert decrypted["age"] == 30

    def test_missing_field_ignored(self):
        with patch("aim.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                encryption_key=self.key,
                encrypted_fields=["email"],
            )
            from aim.utils.encryption import encrypt_fields, reset_encryption
            reset_encryption()

            props = {"name": "Bob"}
            encrypted = encrypt_fields(props, ["email"])
            # No crash, name unchanged
            assert encrypted == {"name": "Bob"}

    def test_decrypt_plaintext_fallback(self):
        """Decrypting a plaintext value should return it as-is (graceful fallback)."""
        with patch("aim.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                encryption_key=self.key,
                encrypted_fields=["email"],
            )
            from aim.utils.encryption import decrypt_value, reset_encryption
            reset_encryption()

            # This is not encrypted — decrypt should return it unchanged
            result = decrypt_value("plain_text_value")
            assert result == "plain_text_value"

    def test_empty_encrypted_fields_list(self):
        with patch("aim.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                encryption_key=self.key,
                encrypted_fields=[],
            )
            from aim.utils.encryption import encrypt_fields, reset_encryption
            reset_encryption()

            props = {"email": "test@test.com"}
            result = encrypt_fields(props, [])
            assert result == props  # empty list → no encryption


class TestEncryptionConfig:
    """Verify encryption config fields exist and have proper defaults."""

    def test_encryption_config_defaults(self):
        from aim.config import Settings

        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "test",
            "NEO4J_PASSWORD": "test",
            "PINECONE_API_KEY": "test",
            "OPENAI_API_KEY": "test",
        }):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                s = Settings()
        assert s.encryption_key == ""
        assert s.encrypted_fields == []

    def test_encryption_config_custom(self):
        from aim.config import Settings

        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "test",
            "NEO4J_PASSWORD": "test",
            "PINECONE_API_KEY": "test",
            "OPENAI_API_KEY": "test",
            "ENCRYPTION_KEY": "test_key_here",
            "ENCRYPTED_FIELDS": '["email","ssn"]',
        }):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                s = Settings()
        assert s.encryption_key == "test_key_here"
        assert s.encrypted_fields == ["email", "ssn"]


class TestNeo4jClientEncryptionWiring:
    """Verify Neo4jClient uses encrypt/decrypt for entity properties."""

    def test_client_stores_encrypted_fields(self):
        """Neo4jClient should read encrypted_fields from settings at init."""
        with patch("aim.graph.neo4j_client._get_driver") as mock_driver, \
             patch("aim.graph.neo4j_client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                neo4j_database="testdb",
                neo4j_query_timeout_seconds=10.0,
                encrypted_fields=["email", "ssn"],
            )
            mock_driver.return_value = MagicMock()

            from aim.graph.neo4j_client import Neo4jClient
            client = Neo4jClient()
            assert client._encrypted_fields == ["email", "ssn"]
