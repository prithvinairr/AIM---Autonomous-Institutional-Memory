# A.1 — Operational Pressure Test Runbook

Concrete procedure for executing Phase A.1 of the customer-ready plan.
Artifacts landed this session build the tooling; **YOU run the commands**
against your stack and record the numbers.

## Prerequisites

- `docker-compose up -d` running cleanly.
- `.env` populated with real keys (or `llm_provider=local` + Ollama running).
- `k6` installed locally (`brew install k6` or equivalent).
- Corpus seeded — run `python -m aim.scripts.seed_demo` first so queries have real data to hit.
- A warmed cache — issue 2–3 queries manually before any drill.

## Run order

### Step 1 — Load test (produces the SLO table)

```bash
export AIM_BASE_URL=http://localhost:8000
export AIM_API_KEY=your-dev-key
k6 run scripts/loadtest/loadtest.js
```

**Output:** terminal summary + `loadtest_summary.json` + per-stage p99/error-rate table.

**Exit criterion (you set the target):**
- `baseline` (2 QPS): p99 ≤ `X` ms, error rate <1%.
- `headroom` (10 QPS): p99 ≤ `3X` ms, error rate <5%.
- `breakpoint` (20 QPS): no pass/fail — document the observed cliff.

Record `X` in your SLO doc. `X=1500` is a reasonable first anchor for the default docker-compose (2 CPU, 2 GB RAM on the aim container).

### Step 2 — Chaos drills (produces the degradation matrix)

Run each drill individually; never two at once.

```bash
bash scripts/loadtest/chaos/neo4j_down.sh
bash scripts/loadtest/chaos/redis_down.sh
bash scripts/loadtest/chaos/pinecone_down.sh
bash scripts/loadtest/chaos/llm_down.sh
```

**Exit criterion:** every drill exits 0 (graceful) or surfaces a structured 503 (fail-loud). A 500 with a stack trace is the A.1 gate failing.

Record: for each drill, paste the PASS/FAIL line + answer-length into the degradation matrix.

### Step 3 — Key rotation (1 command)

```bash
bash scripts/loadtest/rotate_keys.sh
```

**Exit criterion:** prints `PASS — key rotation works as claimed`. Any FAIL line means the rotation story in the config is broken — fix before a security-conscious customer reads the code.

### Step 4 — Memory leak (10k queries)

```bash
python scripts/loadtest/memory_leak.py --queries 10000 --sample-every 500
```

Takes roughly 30–45 minutes on the default docker-compose. Runs unattended — ignore and come back.

**Exit criterion:** growth rate <10 MB per 1k queries after warmup. Higher than that = documented leak; file it before moving on to A.2.

Output: `scripts/loadtest/memory_leak.csv` (plot-friendly), `memory_leak.txt` (summary).

## What "A.1 complete" means

You have, in the repo or an adjacent doc:

- [ ] An SLO table: baseline/headroom/breakpoint p99 latency + error rate, measured on YOUR hardware.
- [ ] A degradation matrix: per-dependency behaviour when killed.
- [ ] A rotation drill receipt: `PASS` output captured.
- [ ] A memory leak receipt: growth-per-1k-queries number captured.
- [ ] A one-paragraph honest writeup of what this test DIDN'T cover (e.g. multi-region, clustered Neo4j, HA Redis) so future reviewers don't overclaim.

Only then proceed to A.2 (benchmark harness).

## Things this test deliberately does NOT cover

- **Multi-region latency** — not in scope for single-worker default.
- **Clustered Neo4j failover** — single-instance docker-compose only.
- **Long-running conversation threads** — conversation load specifically is a separate test.
- **MCP stdio subprocess stress** — MCP is opt-in; load-test the plain `/query` path first.
- **Streaming endpoint** — SSE load behaviour differs; run it as a second pass once the non-stream SLO is known.

If a customer asks about any of these, the honest answer is "not yet tested; here's the subset we have tested."
