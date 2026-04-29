# A.2 — Benchmark Harness Runbook

Phase A.2 turns "AIM beats vanilla RAG" from a structural claim into a number. The gate: `aim_full` must beat `vector_only` on multi-hop NDCG@10 by **≥15pp** AND tie or win (Δ≥0pp) on single-hop. Fail either half and the retrieval pipeline is broken — fix it before moving to A.3 (compliance dossier). A.1 proved the stack stays up under load; A.2 proves the stack is actually better than the strawman it replaces. No PASS here, no customer pitch.

## Prerequisites

- `docker-compose up -d` running cleanly (Neo4j + Redis + Pinecone-compatible vector store reachable).
- Corpus seeded — `python -m aim.scripts.seed_demo` first. Slug → UUID mapping lives in `seed_demo._id()`; the harness relies on it to project fixture slugs.
- `.env` populated with real keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (embeddings), `PINECONE_API_KEY`. Local/stub models will make the numbers meaningless.
- `pip install -e ".[dev]"` — pulls in `pyyaml` which the loader needs. Without it, fixture load raises `ImportError`.
- A warmed cache is NOT wanted here (unlike A.1). If Redis has cached answers from previous runs, `FLUSHDB` first — you want the systems hit end-to-end.

## Fixture

Ground-truth lives at `tests/eval/fixtures/ground_truth.yaml`. If it doesn't exist yet, author it there — the harness CLI defaults to that path.

Schema (one YAML list entry per question):

```yaml
- id: single-001
  question: "Who owns the authentication service?"
  category: single_hop          # single_hop | multi_hop | negative | ambiguous
  gold_answer: "Sarah Chen"     # null for negatives; judge + string matcher use this
  gold_entities:                # slugs — the retriever must surface these
    - svc-auth
    - person-sarah-chen
  gold_path:                    # optional, multi-hop only, order matters
    - svc-auth
    - person-sarah-chen
  gold_sources: []              # optional; specific source_ids the answer must cite
```

**Slug convention**: author slugs (`svc-auth`, `person-sarah-chen`) in the fixture, not raw UUIDs. The harness projects slugs to UUIDs using the same `seed_demo._id()` mapping that populated the graph. Keep slugs stable across fixture revisions so diffs stay readable.

**Distribution target**: roughly **30/40/20/10** single_hop / multi_hop / negative / ambiguous. A fixture weighted 95% single-hop will mask a multi-hop regression — `category_breakdown()` calls this out in the report but nobody reads it if the PASS line is green. Keep the shape honest.

Validation is strict: unknown categories, duplicate ids, `gold_answer: null` on a non-negative, or missing `gold_answer` on a non-negative all raise at load time. Bad fixture → fail fast, not mid-run.

## Run order

### Step 1 — Author or extend the fixture

Target: ≥25 items with the distribution above. Each item needs real gold entities that exist in the seeded graph, or NDCG is structurally zero and the PASS line is a lie.

Check the shape before running anything:

```python
from aim.eval.loader import load_ground_truth, category_breakdown
items = load_ground_truth("tests/eval/fixtures/ground_truth.yaml")
print(len(items), category_breakdown(items))
```

### Step 2 — Run the harness

```bash
python -m aim.eval.harness \
  --fixture tests/eval/fixtures/ground_truth.yaml \
  --out eval_report.md
```

**TODO**: the `__main__` CLI shim is not wired up yet. Until it lands, invoke `run_eval_with_exit` from a short Python script:

```python
import asyncio
from aim.eval import (
    make_vector_only_runner, make_graph_only_runner, make_aim_full_runner,
    render_report,
)
from aim.eval.harness import run_eval_with_exit
from aim.eval.judge import judge_answer  # omit (pass judge=None) for fast iteration

# Build runners against the live stack (your wiring — vector_store, llm,
# embedder, graph_client, entity_extractor, compiled LangGraph agent).
runners = {
    "vector_only": make_vector_only_runner(vector_store=..., llm=..., embedder=...),
    "graph_only":  make_graph_only_runner(graph_client=..., entity_extractor=..., llm=...),
    "aim_full":    make_aim_full_runner(agent=...),
}

results = asyncio.run(run_eval_with_exit(
    fixture_path="tests/eval/fixtures/ground_truth.yaml",
    runners=runners,
    judge=judge_answer,  # or None for a cheap dry-run
))
open("eval_report.md", "w", encoding="utf-8").write(render_report(results))
```

Runtime: set based on your measurement. Expect roughly `n_items × n_systems × per_query_latency` — for 30 items × 3 systems at ~4s/query that's ~6 minutes without judge, longer with.

### Step 3 — Read `eval_report.md`

The exit-criterion section at the bottom is the only line that matters for the gate:

> **Verdict:** `PASS` — AIM full beats vector_only on multi-hop by +17.4pp (≥15pp required) and ties/wins single-hop by +1.2pp.

Above it: overall comparison table, per-category breakdown (single_hop / multi_hop / negative / ambiguous), methodology notes. If the verdict is `UNKNOWN`, your fixture is missing single-hop or multi-hop items — go back to Step 1.

## Exit criteria

A.2 is complete only when every box is ticked:

- [ ] Fixture has **≥25 items** with the 30/40/20/10 distribution shape (verify via `category_breakdown`).
- [ ] Report generated for **all three systems**: `vector_only`, `graph_only`, `aim_full`. No "I'll add graph_only later".
- [ ] Either a **`PASS` verdict** (multi-hop Δ≥15pp, single-hop Δ≥0pp) OR a written action plan for the retrieval layer addressing the specific failure mode (see below).
- [ ] **Per-category NDCG** broken out in the report — single-hop and multi-hop rows both present.
- [ ] **Likert scores present** in the final report (or explicitly disabled with a one-line note explaining why — "judge cost exceeded budget for this revision", etc.).
- [ ] Report committed under `docs/eval/YYYY-MM-DD-<shortdesc>.md` or equivalent date-stamped path. Don't overwrite the last report — diffs across revisions are the receipt trail.

## Interpreting a FAIL

- **Multi-hop regression vs vector_only (Δ < 15pp)**: graph traversal isn't being invoked effectively. Check `reasoning_branch_count`, `evaluator_mode`, and `retrieval_fusion_mode` (should default to `graph_reranks_vector` per the δ.3 flip). A multi-hop failure with graph_only *also* underperforming points at entity extraction or the seed corpus.
- **Single-hop regression (Δ < 0pp)**: the synthesizer is dropping vector hits that vector_only is finding. Usually a fusion-weighting issue — AIM is over-weighting the graph and starving the answer of the chunk it needs. Inspect `retrieval_fusion_mode` and the fusion weights.
- **Both failing**: end-to-end plumbing. Decomposer is injecting the wrong entities, or synthesizer is ignoring the context entirely. Read the `per_item` error rows for ten items and look for the pattern — e.g. empty `retrieved_ids`, empty `cited_ids`, answers that don't reference any gold entity.

Per-item rows are in `results["systems"][name]["per_item"]` — render them as a scratch CSV if eyeballing the Markdown gets painful.

## Judge cost control

Likert uses `llm.invoke` at `temperature=0`, `max_tokens=8`, one call per (item, system) pair. A 30-item × 3-system fixture = **90 judge calls** per run. Scale linearly from there.

Run order to keep the bill honest:

1. First pass, `judge=None`. NDCG / citation / path / neg-reject are all non-LLM — you get the PASS/FAIL verdict without paying for the judge at all.
2. Once the numbers look stable and the verdict is holding, run once more with `judge=judge_answer` for the final report that goes in the dossier.

Re-running with the judge on every fixture tweak is the fast way to burn through budget for no signal.

## Things this test deliberately does NOT cover

- **Fixture size**. 25–35 items is enough to catch a structural regression; a real public-leaderboard submission (HotpotQA, MuSiQue) needs ≥500 items with held-out splits. We're not making a leaderboard claim here.
- **Cross-session consistency**. One YAML, one run. No variance across reseeded graphs or permuted question orderings.
- **Noise robustness**. No paraphrased questions, typos, adversarial prompts, or prompt-injection attempts in the fixture.
- **Judge variance**. Single run per (item, system). No bootstrapped confidence interval on the Likert mean — a 0.2 gap between systems is well inside judge noise and should not be over-interpreted.
- **Ambiguous category rigour**. The `ambiguous` bucket is a placeholder. Scoring genuinely ambiguous answers ("the right answer is 'it depends'") needs a separate rubric we haven't written.
- **Streaming latency / SSE behaviour**. The harness calls `agent.ainvoke` — the non-stream path. Streaming is a separate measurement.
- **MCP fetching**. Runners skip Slack/Jira MCP context. If your prospects care, that's a separate A.x.
- **Conversation-context accuracy**. Single-turn only. Multi-turn coherence, thread-scoped memory, and conversation-history injection are not exercised.

If a reviewer asks about any of the above, the honest answer is "not yet measured; here's the subset we did measure and the fixture is in-repo so you can verify".

## What "A.2 complete" means

Every exit-criterion box above is ticked, `eval_report.md` is committed under `docs/eval/` with a date stamp, and the PASS rationale line (or the action plan for a FAIL) is in the commit message. Receipts filed. Only then proceed to A.3 (compliance dossier).
