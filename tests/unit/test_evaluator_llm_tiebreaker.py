"""Phase δ.3 Move 3 — LLM tiebreaker for branch selection.

Panel audit (2026-04-19) Hallmark 4 gap: branch fan-out + static
heuristic scoring gives us parallelism but not *adaptive* tree-of-
thought. When the heuristic is genuinely uncertain — two branches
within a whisker of each other — committing to the heuristic winner
is a coin flip.

δ.3 Move 3 (Option B from the plan) adds a third evaluator tier
``"llm_tiebreaker"``. Heuristic still scores every branch. LLM only
fires when ``top - runner_up < evaluator_llm_tiebreaker_threshold``
(default 0.1). Result: near-zero cost in the common case, LLM
judgement available where it actually matters.

This suite pins:

1. Config shape — new knob, new mode, old modes still valid.
2. Selector primitive — clear winner skips LLM; tie invokes judge;
   judge failure degrades gracefully to heuristic winner; judge
   returning an unknown branch_id also degrades gracefully.
3. Telemetry — the ``judge_invoked`` flag reflects reality (for ops
   dashboards that want to count tiebreaker activations).
"""
from __future__ import annotations

import pytest

from aim.agents.branch_selector import (
    BranchCandidate,
    select_best_with_tiebreaker,
)


def _cand(bid: str, *, answer_len: int = 200, cited: int = 5, total: int = 5,
          covered: int = 3, total_sq: int = 3, confidence: float = 0.8) -> BranchCandidate:
    return BranchCandidate(
        branch_id=bid,
        answer_text="x" * answer_len,
        cited_source_ids=tuple(f"s{i}" for i in range(cited)),
        total_sources=total,
        covered_sub_queries=covered,
        total_sub_queries=total_sq,
        confidence=confidence,
    )


class TestConfigGate:
    def test_default_evaluator_mode_unchanged(self):
        """Move 3 is OPT-IN. Default stays 'heuristic' so existing
        deployments don't start paying LLM tokens on every fan-out."""
        from aim.config import Settings
        s = Settings(
            anthropic_api_key="sk-test",
            openai_api_key="sk-test",
            neo4j_password="test",
            pinecone_api_key="test",
        )
        assert s.evaluator_mode == "heuristic"

    def test_llm_tiebreaker_mode_accepted(self):
        from aim.config import Settings
        s = Settings(
            anthropic_api_key="sk-test",
            openai_api_key="sk-test",
            neo4j_password="test",
            pinecone_api_key="test",
            evaluator_mode="llm_tiebreaker",
        )
        assert s.evaluator_mode == "llm_tiebreaker"

    def test_threshold_default_is_reasonable(self):
        """Default 0.1 = top-two within 10% of full score range.
        Large enough to catch genuine ties, small enough not to fire
        on 90%+ of clean fan-outs."""
        from aim.config import Settings
        s = Settings(
            anthropic_api_key="sk-test",
            openai_api_key="sk-test",
            neo4j_password="test",
            pinecone_api_key="test",
        )
        assert 0.0 < s.evaluator_llm_tiebreaker_threshold <= 0.25

    def test_threshold_must_be_in_range(self):
        from aim.config import Settings
        with pytest.raises(Exception):  # pydantic ValidationError
            Settings(
                anthropic_api_key="sk-test",
                openai_api_key="sk-test",
                neo4j_password="test",
                pinecone_api_key="test",
                evaluator_llm_tiebreaker_threshold=1.5,
            )

    def test_invalid_evaluator_mode_rejected(self):
        from aim.config import Settings
        with pytest.raises(Exception):  # pydantic ValidationError
            Settings(
                anthropic_api_key="sk-test",
                openai_api_key="sk-test",
                neo4j_password="test",
                pinecone_api_key="test",
                evaluator_mode="not_a_real_mode",
            )


class TestSelectBestWithTiebreaker:
    @pytest.mark.asyncio
    async def test_clear_winner_skips_judge(self):
        """When heuristic spread is comfortably above threshold, the
        judge must NEVER be invoked — this is the whole point of
        Option B (zero LLM cost in the common case)."""
        calls = []

        async def judge(contenders):
            calls.append([c.branch_id for c in contenders])
            return contenders[0].branch_id

        # Clear winner: full citation + full coverage vs. weak branch.
        strong = _cand("strong", cited=5, total=5, covered=3, total_sq=3,
                       confidence=0.9, answer_len=400)
        weak = _cand("weak", cited=1, total=5, covered=1, total_sq=3,
                     confidence=0.3, answer_len=50)

        winner, _scores, invoked = await select_best_with_tiebreaker(
            [strong, weak], threshold=0.1, judge=judge,
        )
        assert winner.branch_id == "strong"
        assert invoked is False
        assert calls == [], "judge must not be called on a clear winner"

    @pytest.mark.asyncio
    async def test_near_tie_invokes_judge(self):
        """When heuristic spread is below threshold, the judge MUST
        fire and its pick MUST win — even if it's not the heuristic
        winner. That's what adaptive tree-of-thought means here."""
        seen = {}

        async def judge(contenders):
            seen["ids"] = [c.branch_id for c in contenders]
            # Deliberately pick the runner-up to prove the judge's
            # vote actually overrides the heuristic.
            return contenders[-1].branch_id

        # Two near-identical candidates (same everything).
        a = _cand("a", confidence=0.80)
        b = _cand("b", confidence=0.79)  # trivially lower

        winner, _scores, invoked = await select_best_with_tiebreaker(
            [a, b], threshold=0.1, judge=judge,
        )
        assert invoked is True
        assert "ids" in seen and set(seen["ids"]) == {"a", "b"}
        # Judge picked b, and b wins despite a's slightly higher score.
        assert winner.branch_id == "b"

    @pytest.mark.asyncio
    async def test_judge_exception_falls_back_to_heuristic(self):
        """Judges are best-effort. If the LLM call raises (network,
        rate limit, provider outage), we MUST NOT propagate — the
        heuristic winner is a perfectly valid answer."""
        async def judge(_contenders):
            raise RuntimeError("judge is down")

        a = _cand("a", confidence=0.80)
        b = _cand("b", confidence=0.79)

        winner, _scores, invoked = await select_best_with_tiebreaker(
            [a, b], threshold=0.1, judge=judge,
        )
        # a has the higher heuristic score → it wins the fallback.
        assert winner.branch_id == "a"
        # invoked=False documents that the judge didn't produce a vote.
        assert invoked is False

    @pytest.mark.asyncio
    async def test_judge_unknown_id_falls_back(self):
        """If the LLM returns a branch_id not in the contender set
        (hallucination, truncation), treat it as a judge failure."""
        async def judge(_contenders):
            return "not-a-real-branch-id"

        a = _cand("a", confidence=0.80)
        b = _cand("b", confidence=0.79)

        winner, _scores, invoked = await select_best_with_tiebreaker(
            [a, b], threshold=0.1, judge=judge,
        )
        assert winner.branch_id == "a"  # heuristic fallback
        assert invoked is False

    @pytest.mark.asyncio
    async def test_none_judge_equivalent_to_heuristic(self):
        """Passing judge=None must be a drop-in for select_best —
        lets callers enable/disable the tier by swapping the judge
        argument without branching their call site."""
        a = _cand("a", confidence=0.80)
        b = _cand("b", confidence=0.79)

        winner, _scores, invoked = await select_best_with_tiebreaker(
            [a, b], threshold=0.1, judge=None,
        )
        assert winner.branch_id == "a"
        assert invoked is False

    @pytest.mark.asyncio
    async def test_single_candidate_skips_judge(self):
        """With only one candidate there is no tie to break. Judge
        must not fire even though threshold would otherwise apply."""
        called = []

        async def judge(contenders):
            called.append(True)
            return contenders[0].branch_id

        a = _cand("solo", confidence=0.5)
        winner, _scores, invoked = await select_best_with_tiebreaker(
            [a], threshold=0.1, judge=judge,
        )
        assert winner.branch_id == "solo"
        assert invoked is False
        assert called == []

    @pytest.mark.asyncio
    async def test_threshold_zero_disables_judge(self):
        """A zero threshold means 'never tied' — the judge is opt-in
        via threshold, so operators can kill the LLM path without
        changing modes."""
        called = []

        async def judge(contenders):
            called.append(True)
            return contenders[0].branch_id

        # Even identical scores shouldn't trip threshold=0 (strict <).
        a = _cand("a")
        b = _cand("b")

        winner, _scores, invoked = await select_best_with_tiebreaker(
            [a, b], threshold=0.0, judge=judge,
        )
        assert invoked is False
        assert called == []
        # Stable sort: earlier branch wins on exact tie.
        assert winner.branch_id == "a"

    @pytest.mark.asyncio
    async def test_three_way_tie_passes_all_contenders(self):
        """If three branches are within threshold, all three go to
        the judge — not just the top-two. A two-stage bracket would
        lose information about the third contender."""
        seen = {}

        async def judge(contenders):
            seen["ids"] = sorted(c.branch_id for c in contenders)
            return contenders[0].branch_id

        a = _cand("a", confidence=0.82)
        b = _cand("b", confidence=0.80)
        c = _cand("c", confidence=0.79)

        winner, _scores, invoked = await select_best_with_tiebreaker(
            [a, b, c], threshold=0.1, judge=judge,
        )
        assert invoked is True
        assert seen["ids"] == ["a", "b", "c"]
        assert winner.branch_id == "a"  # judge's pick

    @pytest.mark.asyncio
    async def test_empty_candidates_raises(self):
        async def judge(_contenders):
            return ""

        with pytest.raises(ValueError):
            await select_best_with_tiebreaker(
                [], threshold=0.1, judge=judge,
            )
