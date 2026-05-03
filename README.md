<p align="center">
  <strong>AIM</strong>
</p>

<h1 align="center">Autonomous Institutional Memory</h1>

<p align="center">
  A local-first GraphRAG system that turns engineering context into a queryable,
  provenance-aware memory layer.
</p>

<p align="center">
  <a href="#run-locally">Run locally</a> ·
  <a href="#benchmark">Benchmark</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#slack-live-ingest">Slack ingest</a> ·
  <a href="LIMITATIONS.md">Limitations</a>
</p>

<p align="center">
  <img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-Agent-1f6feb?style=flat-square">
  <img alt="Neo4j" src="https://img.shields.io/badge/Neo4j-Knowledge_Graph-4581C3?style=flat-square&logo=neo4j&logoColor=white">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-Frontend-000000?style=flat-square&logo=nextdotjs&logoColor=white">
  <img alt="Local first" src="https://img.shields.io/badge/Local--first-Ollama%20%2B%20Qdrant-22c55e?style=flat-square">
</p>

<p align="center">
  <img src="docs/images/aim-dashboard-answer.png" alt="AIM dashboard answering an incident query with retrieved sources, knowledge nebula, and provenance-backed synthesis" width="100%">
</p>

## Overview

Most workplace RAG systems are document search with a chat box. AIM is built for
questions where the answer is a relationship, not a paragraph:

- Which service did this incident affect?
- Who responded, and which team reported it?
- Which decision superseded the policy that caused the outage?
- What path connects a Slack message, a runbook, a service, and an owner?

AIM ingests operational context, extracts typed entities and relationships,
stores them in Neo4j and Qdrant, and answers with evidence paths instead of flat
snippets. The goal is not just retrieval. The goal is institutional memory that
can explain where an answer came from.

## What AIM Does

| Capability | What it means |
|---|---|
| Live Slack ingest | Slack Events API -> signed FastAPI webhook -> extractor -> Neo4j + Qdrant in seconds. |
| GraphRAG + vector retrieval | Typed graph traversal is combined with semantic vector search. |
| Multi-hop reasoning | The agent decomposes a query, expands graph neighborhoods, scores paths, and synthesizes a grounded answer. |
| Provenance maps | Responses carry graph nodes, graph edges, source IDs, citations, and a reasoning trace. |
| Exact-incident guardrails | Direct incident questions answer from recorded facts or abstain; nearby incidents are not allowed to bleed in. |
| Local-first inference | The default path runs with Ollama and local embeddings. API-backed models are optional. |
| Demo-grade frontend | Next.js console with retrieved sources, streaming status, and a 3D knowledge nebula. |

## Demo Flow

| Live ingest | Streaming retrieval | Grounded answer |
|---|---|---|
| <img src="docs/images/slack-live-ingest.png" alt="Slack workspace with live incident messages flowing into AIM"> | <img src="docs/images/aim-dashboard-thinking.png" alt="AIM frontend while a deep query is processing"> | <img src="docs/images/aim-dashboard-answer.png" alt="AIM frontend after answering an incident query"> |

The important part: there is no nightly re-indexing job in this demo path. A
Slack message arrives, AIM extracts entities and relationships, writes graph and
vector records, and the next query can retrieve the new fact.

## Benchmark

Latest saved run: [`docs/benchmarks/eval_report_after_teacher_bfs.md`](docs/benchmarks/eval_report_after_teacher_bfs.md)

Fixture: 34 gold-labeled items in [`tests/eval/fixtures/ground_truth.yaml`](tests/eval/fixtures/ground_truth.yaml)

| System | Overall NDCG@10 | Multi-hop NDCG@10 | Multi-hop Path Acc | Multi-hop Citation | p50 Latency |
|---|---:|---:|---:|---:|---:|
| `vector_only` | 0.344 | 0.460 | 0.000 | 0.393 | 6.2s |
| `graph_only` | 0.548 | 0.799 | 0.720 | **0.500** | **6.3s** |
| **`aim_full`** | **0.659** | **0.836** | **0.839** | 0.363 | 29.1s |

What this supports:

- AIM beats `vector_only` by **+37.7 percentage points** on multi-hop NDCG.
- AIM beats `graph_only` on **overall NDCG**, **multi-hop NDCG**, and
  **multi-hop path accuracy**.
- `graph_only` still wins on citation precision and latency.

This is not a SOTA claim. It is evidence that AIM is more than a standard vector
RAG wrapper on this fixture. Full methodology, ablations, and per-category
tables are in [`BENCHMARKS.md`](BENCHMARKS.md).

## Architecture

```text
Slack / Jira / Confluence
        |
        v
FastAPI signed webhooks
        |
        v
Ingest worker -> LLM extractor -> deduplicator -> Neo4j + Qdrant

User query
        |
        v
FastAPI /query or /query/stream
        |
        v
LangGraph agent
  decomposer        -> sub-queries, intent, entity pairs
  graph_searcher    -> Neo4j hybrid search, path scoring, exact-incident checks
  vector_retriever  -> Qdrant approximate nearest neighbor retrieval
  mcp_fetcher       -> optional live tool/context fetch
  synthesizer       -> grounded answer, citations, provenance graph
        |
        v
Next.js frontend -> decision console, sources, knowledge nebula
```

Single-worker note: the compiled LangGraph and in-process token buckets are
module-level singletons. Run one worker per process and scale horizontally behind
a load balancer.

## Stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI | Async routes, signed webhooks, SSE streaming. |
| Agent orchestration | LangGraph | Stateful graph pipeline with reducers and parallel fan-out. |
| Knowledge graph | Neo4j 5.24 + APOC | Cypher path queries with fulltext and vector indexes nearby. |
| Vector store | Qdrant by default, Pinecone optional | Local-first by default; hosted option available. |
| LLM | Ollama-compatible local model by default | Keeps the full demo runnable without paid API keys. |
| API LLMs | Anthropic or OpenAI optional | Higher-quality synthesis path when keys are available. |
| Embeddings | `nomic-embed-text` | Local 768-dimensional embeddings. |
| Frontend | Next.js standalone | Production build can run with Node directly. |
| Cache and threads | Redis optional | Falls back to in-memory behavior when Redis is absent. |
| Webhook security | HMAC-SHA256 | Slack-style signing-secret verification with replay checks. |

## Run Locally

Requires Python 3.12+, Node 22+, Neo4j 5.24+, Qdrant 1.11+, and either Ollama
for local-LLM mode or an Anthropic/OpenAI API key.

Backend:

```bash
pip install -e ".[dev]"
cp .env.example .env

# Set NEO4J_PASSWORD at minimum.
# Start Neo4j on bolt://localhost:7687
# Start Qdrant on http://localhost:6333
# Start Ollama on http://localhost:11434/v1, or configure an API LLM provider.

python -m aim.scripts.seed_demo
uvicorn aim.main:app --workers 1 --port 8000
```

Frontend:

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run build
node .next/standalone/server.js
```

Open `http://localhost:3000`.

Do not use `next start` for this project. The frontend is configured for the
Next.js standalone runner.

## Public Demo With Cloudflare Tunnel

For a temporary public demo without committing secrets:

```bash
# Backend
cloudflared tunnel --url http://localhost:8000

# Frontend, in a separate terminal
cloudflared tunnel --url http://localhost:3000
```

Share the frontend tunnel URL. Use the backend tunnel URL for webhook providers:

```text
https://<your-backend-tunnel>/webhooks/slack/events
```

Quick-tunnel URLs are temporary and change when `cloudflared` restarts. For a
permanent demo, use a named Cloudflare tunnel with a custom domain, or deploy
the Next.js frontend to a platform such as Vercel and host the backend
separately.

## Slack Live Ingest

1. Create a Slack app.
2. Set `WEBHOOK_SLACK_SIGNING_SECRET` and `SLACK_BOT_TOKEN` in `.env`.
3. Expose the backend with a tunnel.
4. Set Slack Event Subscriptions to:

   ```text
   https://<tunnel>/webhooks/slack/events
   ```

5. Subscribe to `message.channels`, reinstall the app, and invite the bot to a
   channel.
6. Post a relationship-explicit incident message:

   ```text
   INC-2025-100 was caused by the Auth Service rate limiter rejecting requests
   after the 10am deploy. Marcus from the SRE team is leading the rollback.
   ```

7. Ask AIM:

   ```text
   Which service did INC-2025-100 affect, and who is leading the response?
   ```

Live extraction works best when messages include explicit relationship language:
`caused by`, `impacted`, `owned by`, `approved by`, `reported by`, `leading`, or
`superseded`. If the graph does not contain the edge, AIM is designed to answer
narrowly or abstain instead of borrowing facts from nearby incidents.

You can also replay a signed Slack event locally:

```bash
python scripts/replay_slack_event.py
```

## Tests And Evaluation

```bash
pytest
PYTHONIOENCODING=utf-8 python scripts/eval_live.py --out eval_report.md
```

Targeted checks for incident guardrails and streaming:

```bash
pytest tests/unit/test_exact_incident_fast_path.py \
       tests/unit/test_extraction.py \
       tests/integration/test_streaming.py
```

The live benchmark runs `vector_only`, `graph_only`, and `aim_full` against the
same fixture and reports NDCG, path accuracy, citation behavior, negative
rejection, and p50 latency.

## Limitations

AIM is ready to demo and evaluate, but it is still a research-grade system. The
core graph retrieval loop is working; the remaining work is larger evaluation,
production hardening, and reducing dependence on small local models.

- The benchmark is intentionally transparent but small: 34 labeled questions.
  The next serious validation step is HotpotQA, MuSiQue, or 2WikiMultihopQA.
- Citation quality is the weakest measured area on the local model path. The
  graph often finds the right path, but the local synthesizer is not always
  disciplined about citing it.
- Deep multi-hop answers are not instant. The saved eval run has a p50 latency
  of 29.1 seconds for `aim_full`.
- Slack ingest has been exercised end-to-end. Jira and Confluence support are
  represented in the architecture, but need real-workspace soak testing.
- Before production use, the security layer needs a deployment-specific pass for
  prompt injection, PII redaction, tenant access policy, retention, and audit
  logging.

The detailed roadmap is in [`LIMITATIONS.md`](LIMITATIONS.md).

## Notable Implementation Detail

The most important retrieval improvement is in
[`aim/agents/nodes/graph_searcher.py`](aim/agents/nodes/graph_searcher.py):
score boosting by path participation.

Multi-hop answers are often complete paths, not isolated nodes. Hybrid search
can find an intermediate node as a 2-hop neighbor, but because the intermediate
name does not always text-match the query, it can land outside NDCG@10. AIM
boosts entities that appear on discovered paths and re-sorts the graph results.
That lifts path intermediates into the top results without inventing new facts.

## Publishing And Secrets

This repository is structured so it can be shared publicly without exposing
local credentials or runtime state. Real API keys and deployment-specific
configuration belong in `.env` and `frontend/.env.local`; both are excluded from
version control. The committed example files document the required variables
without containing working secrets.

Recommended release checks:

```bash
npm --prefix frontend audit --audit-level=moderate
python -m pip_audit
python -m pytest -p no:cacheprovider tests/unit tests/eval -q
```

## Credits

Built solo in April 2026 as an exploration of what graph-backed retrieval can
add beyond vector RAG, and what an institutional-memory tool would need before
it becomes useful inside an engineering organization.
