"""Phase α.1 — embedding sovereignty by default.

The audit flagged ``get_embedding_provider()`` as a real leak vector:
the prior default of ``embedding_provider="openai"`` meant every query
and every ingested document flowed through OpenAI, with no classification
check.

This phase makes the sovereignty story *structural* rather than
*guarded*: the default is ``local``, and selecting ``local`` requires
an explicit base URL (previously the check lived inside
``get_embedding_provider()`` and only fired at first query).

What this pins:
* ``embedding_provider`` default is ``"local"``.
* ``local`` without an explicit base URL is a ValidationError at config
  load, not a deferred RuntimeError at query time.
* ``openai`` is still selectable for operators who opt in (with a key).
* ``openai`` without an API key still warns in non-production (existing
  behaviour), unchanged.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from aim.config import Settings


class TestEmbeddingDefaultIsLocal:
    def test_default_embedding_provider_is_local(self):
        # With a base URL supplied, local must be the default and must
        # validate cleanly. A Neo4j password is the only other non-embedding
        # credential the model requires, so supply that too.
        s = Settings(
            embedding_base_url="http://localhost:11434/v1",
            neo4j_password="x",
        )
        assert s.embedding_provider == "local"


class TestLocalRequiresBaseUrl:
    def test_local_without_base_url_raises_at_config_time(self):
        """The whole point of moving this check into the validator: the
        failure must be at Settings construction, not deferred until the
        vector retriever runs its first query."""
        with pytest.raises(ValidationError) as excinfo:
            Settings(
                embedding_provider="local",
                embedding_base_url="",
                neo4j_password="x",
            )
        msg = str(excinfo.value).lower()
        assert "embedding_base_url" in msg or "embedding_provider" in msg
        assert "local" in msg

    def test_local_with_base_url_validates(self):
        s = Settings(
            embedding_provider="local",
            embedding_base_url="http://localhost:11434/v1",
            neo4j_password="x",
        )
        assert s.embedding_provider == "local"
        assert s.embedding_base_url == "http://localhost:11434/v1"


class TestOpenAIStillSelectable:
    """Operators who explicitly opt in to OpenAI embeddings (with a key)
    must still be able to do so — the change is about the default, not
    about removing OpenAI as an option."""

    def test_openai_with_key_validates(self):
        s = Settings(
            embedding_provider="openai",
            openai_api_key="sk-test-key",
            neo4j_password="x",
        )
        assert s.embedding_provider == "openai"

    def test_openai_base_url_not_required(self):
        """OpenAI embedding provider talks to api.openai.com by default —
        no base URL needed. The new validator must not accidentally
        require it for the openai path."""
        s = Settings(
            embedding_provider="openai",
            openai_api_key="sk-test-key",
            embedding_base_url="",
            neo4j_password="x",
        )
        assert s.embedding_base_url == ""
