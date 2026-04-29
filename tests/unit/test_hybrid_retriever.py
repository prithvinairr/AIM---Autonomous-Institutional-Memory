"""Phase γ.1 — retrieval fusion.

Pins the pure-function contract of ``aim.agents.hybrid_retriever``:

* ``fuse_by_graph_rerank`` gives a configurable additive boost to vector
  snippets whose ``metadata.entity_id`` appears in the graph-retrieved
  entity set, and re-sorts by the fused score.
* The original input list is never mutated; each returned dict carries a
  ``fused_score`` and a ``graph_matched`` flag for observability.
* ``derive_seed_entity_ids`` extracts entity IDs from the top-k vector
  snippets, deduplicated in score-descending order.

Config-level pins (``retrieval_fusion_mode`` validator, default
``"parallel"``) are exercised here as well because the fusion mode is
meaningless without the gate.
"""
from __future__ import annotations

import pytest

from aim.agents.hybrid_retriever import (
    derive_seed_entity_ids,
    fuse_by_graph_rerank,
)


def _snip(eid: str | None, score: float, text: str = "") -> dict:
    md = {}
    if eid is not None:
        md["entity_id"] = eid
    return {"score": score, "text": text or f"snip-{eid}", "metadata": md}


class TestFuseByGraphRerank:
    def test_matched_snippet_gets_boost(self):
        snips = [_snip("e1", 0.50), _snip("e2", 0.60)]
        fused = fuse_by_graph_rerank(["e1"], snips, boost=0.2)
        # e1 fused = 0.70, e2 fused = 0.60 → e1 now leads.
        assert fused[0]["metadata"]["entity_id"] == "e1"
        assert fused[0]["fused_score"] == pytest.approx(0.70)
        assert fused[0]["graph_matched"] is True
        assert fused[1]["fused_score"] == pytest.approx(0.60)
        assert fused[1]["graph_matched"] is False

    def test_no_match_no_boost(self):
        snips = [_snip("e1", 0.50), _snip("e2", 0.60)]
        fused = fuse_by_graph_rerank(["e99"], snips, boost=0.2)
        # Nothing boosted — order purely by original score.
        assert [s["metadata"]["entity_id"] for s in fused] == ["e2", "e1"]
        for s in fused:
            assert s["graph_matched"] is False
            assert s["fused_score"] == s["score"]

    def test_original_list_not_mutated(self):
        snips = [_snip("e1", 0.50), _snip("e2", 0.60)]
        snapshot = [dict(s) for s in snips]
        fuse_by_graph_rerank(["e1"], snips, boost=0.2)
        # Original dicts unchanged.
        for before, after in zip(snapshot, snips):
            assert before == after
            assert "fused_score" not in after
            assert "graph_matched" not in after

    def test_empty_inputs(self):
        assert fuse_by_graph_rerank([], []) == []
        assert fuse_by_graph_rerank(["e1"], []) == []
        # Empty entity set → behavior-equivalent to no boost.
        fused = fuse_by_graph_rerank([], [_snip("e1", 0.5)])
        assert fused[0]["graph_matched"] is False
        assert fused[0]["fused_score"] == pytest.approx(0.5)

    def test_snippet_without_entity_id_never_matches(self):
        snips = [_snip(None, 0.9), _snip("e1", 0.4)]
        fused = fuse_by_graph_rerank(["e1"], snips, boost=0.2)
        # None-eid snippet should never match even against non-empty set.
        none_snip = next(s for s in fused if not s["metadata"])
        assert none_snip["graph_matched"] is False

    def test_boost_default_is_reasonable(self):
        # Default boost should be strong enough to flip a tie but not so
        # strong that it steamrolls a clearly-stronger raw score.
        fused = fuse_by_graph_rerank(
            ["e1"],
            [_snip("e2", 0.80), _snip("e1", 0.70)],
        )
        # e1 boosted to ~0.85 — wins against 0.80.
        assert fused[0]["metadata"]["entity_id"] == "e1"
        # But a raw 0.30 boosted is still < 0.80:
        fused2 = fuse_by_graph_rerank(
            ["e1"],
            [_snip("e2", 0.80), _snip("e1", 0.30)],
        )
        assert fused2[0]["metadata"]["entity_id"] == "e2"

    def test_filters_out_empty_entity_ids_from_graph_set(self):
        # Empty strings must not accidentally match snippets missing eids.
        fused = fuse_by_graph_rerank(
            ["", None, "e1"],  # type: ignore[list-item]
            [_snip("", 0.9), _snip("e1", 0.2)],
        )
        # "" entity_id never boosted; e1 is.
        empty_snip = next(s for s in fused if s["metadata"].get("entity_id") == "")
        assert empty_snip["graph_matched"] is False


class TestDeriveSeedEntityIds:
    def test_returns_top_k_in_score_order(self):
        snips = [
            _snip("e1", 0.10),
            _snip("e2", 0.90),
            _snip("e3", 0.50),
        ]
        assert derive_seed_entity_ids(snips, top_k=2) == ["e2", "e3"]

    def test_dedups_preserving_first_seen(self):
        snips = [
            _snip("e1", 0.90),
            _snip("e1", 0.80),  # duplicate — drop
            _snip("e2", 0.70),
        ]
        assert derive_seed_entity_ids(snips, top_k=5) == ["e1", "e2"]

    def test_skips_snippets_without_entity_id(self):
        snips = [_snip(None, 0.99), _snip("e1", 0.40)]
        assert derive_seed_entity_ids(snips, top_k=3) == ["e1"]

    def test_empty_input(self):
        assert derive_seed_entity_ids([], top_k=5) == []


class TestConfigGate:
    def test_default_mode_is_graph_reranks_vector(self):
        """δ.3: default flipped from "parallel" to "graph_reranks_vector"
        so graph-structural evidence reshapes the vector ranking in the
        default runtime. ``parallel`` remains the legacy escape hatch."""
        from aim.config import Settings
        # Don't touch other defaults — just check the new knob.
        s = Settings(
            anthropic_api_key="sk-test",
            openai_api_key="sk-test",
            neo4j_password="test",
            pinecone_api_key="test",
        )
        assert s.retrieval_fusion_mode == "graph_reranks_vector"
        assert 0.0 <= s.retrieval_fusion_boost <= 1.0

    def test_graph_reranks_vector_is_accepted(self):
        from aim.config import Settings
        s = Settings(
            anthropic_api_key="sk-test",
            openai_api_key="sk-test",
            neo4j_password="test",
            pinecone_api_key="test",
            retrieval_fusion_mode="graph_reranks_vector",
        )
        assert s.retrieval_fusion_mode == "graph_reranks_vector"

    def test_invalid_mode_rejected(self):
        from aim.config import Settings
        with pytest.raises(Exception):  # pydantic ValidationError
            Settings(
                anthropic_api_key="sk-test",
                openai_api_key="sk-test",
                neo4j_password="test",
                pinecone_api_key="test",
                retrieval_fusion_mode="nonsense",
            )
