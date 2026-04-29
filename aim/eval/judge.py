"""LLM-judge for answer quality (1–5 Likert).

Cheap, deterministic, IO-bound. We use a small/fast model to keep eval
costs reasonable — scoring 100 items at Likert against `claude-opus-4-6`
would waste budget on a task where a 3B local model does fine.

Design:

* One async function, ``judge_answer``, no class. Stateless by design
  so the harness can ``asyncio.gather`` a batch without surprises.
* Strict parsing: prompt asks for a single integer 1–5 on the first
  line; we parse that. If parsing fails, return ``None`` — the harness
  records "judge error" and the metric drops that item rather than
  silently imputing a score.
* Fail-soft on provider error: returns ``None`` on any exception,
  logs at WARN. A flaky judge should not sink the whole eval run.
* Zero-temperature to reduce variance across repeated eval runs so a
  numeric delta reflects system change, not judge noise.

Prompt philosophy (matches the customer plan): rubric is graded on
fidelity to `gold_answer` and grounding in retrieved sources, NOT on
style. We don't want the judge rewarding verbose answers.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Protocol

log = logging.getLogger(__name__)


_LIKERT_RUBRIC = """\
You are a strict evaluator rating an answer on a 5-point Likert scale.

Score strictly:
  5 — answer is factually correct, grounded in sources, matches the gold answer
  4 — answer is mostly correct with minor omissions
  3 — answer is partially correct but missing key facts
  2 — answer is mostly wrong or weakly grounded
  1 — answer is wrong, hallucinated, or off-topic

Respond with a single integer (1–5) on the first line. Nothing else.
"""


class _LLMLike(Protocol):
    async def invoke(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = ...,
        max_tokens: int = ...,
    ) -> Any: ...


async def judge_answer(
    *,
    question: str,
    gold_answer: str | None,
    system_answer: str,
    llm: _LLMLike,
    model_hint: str | None = None,
) -> int | None:
    """Return Likert 1..5 or None on parse/provider failure.

    ``gold_answer`` may be None for negative questions — in that case the
    judge is told the correct response is a refusal. This keeps the
    rubric uniform across categories (one metric, four fixture types).
    """
    if gold_answer is None:
        gold_clause = (
            "There is NO answer in the corpus. The correct response is "
            "\"I don't know\" or an explicit refusal. Any confident "
            "factual claim is a hallucination and scores 1."
        )
    else:
        gold_clause = f"Gold answer: {gold_answer}"

    user = (
        f"Question: {question}\n"
        f"{gold_clause}\n\n"
        f"System answer:\n{system_answer}\n\n"
        "Score (1–5, first line only):"
    )

    try:
        resp = await llm.invoke(
            [
                {"role": "system", "content": _LIKERT_RUBRIC},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=8,
        )
    except Exception as exc:  # noqa: BLE001 — fail-soft by design
        log.warning("judge.invoke failed: %s", exc)
        return None

    content = getattr(resp, "content", "") or ""
    return _parse_likert(content)


def _parse_likert(text: str) -> int | None:
    """Extract the first integer 1–5 from the response.

    We accept a leading integer on the first line; anything else (empty,
    "five", "4.5") returns None. Strictness here is a feature — a judge
    that can't output an integer when asked shouldn't be trusted.
    """
    if not text:
        return None
    first_line = text.strip().splitlines()[0].strip() if text.strip() else ""
    match = re.match(r"^\s*([1-5])\b", first_line)
    if not match:
        return None
    return int(match.group(1))
