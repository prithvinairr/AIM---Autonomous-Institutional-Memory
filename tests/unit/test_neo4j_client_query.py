"""Unit tests for Neo4j query input handling."""
from __future__ import annotations

from aim.graph.neo4j_client import _safe_fulltext_query


def test_safe_fulltext_query_strips_lucene_reserved_characters():
    query = "Which ADR was authored by [owner of the auth service]?"

    assert _safe_fulltext_query(query) == (
        "Which ADR was authored by owner of the auth service"
    )


def test_safe_fulltext_query_never_returns_empty_query():
    assert _safe_fulltext_query("[] ?:") == "*"
