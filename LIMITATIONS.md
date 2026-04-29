# AIM Limitations And Roadmap

AIM is a serious prototype, not a finished enterprise product. This document is
intentionally direct so the repo can be shown to hiring managers or technical
reviewers without hiding the hard parts.

## What Works Now

- Live Slack ingest through a signed webhook.
- Deterministic extraction hardening for incident messages.
- Neo4j graph search with typed entities and relationships.
- Vector retrieval with local-first Qdrant support.
- Hybrid graph + vector agent pipeline.
- Streaming query endpoint.
- Provenance maps with source IDs, graph nodes, and graph edges.
- Exact-incident guardrail: answer from recorded facts or abstain.
- Local-first LLM/embedding mode through an OpenAI-compatible server.
- Benchmark harness comparing `vector_only`, `graph_only`, and `aim_full`.

## Current Strengths

### Multi-Hop Retrieval

The latest saved benchmark has AIM beating graph-only on multi-hop NDCG and path
accuracy:

| Metric | graph_only | aim_full |
|---|---:|---:|
| Multi-hop NDCG@10 | 0.799 | **0.836** |
| Multi-hop path accuracy | 0.720 | **0.839** |

That is the strongest technical result in the repo.

### Exact Incident Safety

For direct incident questions like:

```text
Which service does INC-2025-100 affect?
```

AIM now checks the exact incident graph record first. If an `IMPACTED` or
`AFFECTS` edge exists, it answers from that edge. If the edge is missing, it
says the graph does not contain that fact instead of pulling a similar incident.

This is the right enterprise failure mode.

## Current Gaps

### Citation Precision

Latest saved multi-hop citation:

| System | Multi-hop citation |
|---|---:|
| graph_only | **0.500** |
| aim_full | 0.363 |

AIM finds strong graph paths, but local Qwen is not yet disciplined enough at
citing the exact supporting source IDs. This needs either a better model or a
citation-repair pass.

### Latency

Latest saved p50 latency:

| System | Overall p50 | Multi-hop p50 |
|---|---:|---:|
| graph_only | 6.322s | 8.959s |
| aim_full | 29.105s | 30.180s |

This is acceptable for a demo and for some offline research workflows, but too
slow for a polished enterprise assistant. The bottleneck is local LLM synthesis.

### Small Fixture

The main fixture has 34 items. It is useful for regression testing, but not
enough to claim general dominance over GraphRAG/LightRAG/HippoRAG.

### Live Integrations

Slack has been exercised end-to-end. Jira and Confluence have webhook routes and
MCP/provider scaffolding, but need real workspace integration tests and payload
parsers before they should be called production-ready.

### Prompt Injection And PII

The system has data classification and access-control scaffolding, but it has
not had a full prompt-injection, malicious Slack message, or PII redaction audit.

### Deployment Smoothness

The local stack still has too many moving parts:

- Neo4j
- Qdrant
- Ollama/local LLM
- optional Redis
- FastAPI backend
- Next.js frontend
- optional Cloudflare tunnel

This needs a clean compose file or one-command local runner before outside users
can clone and run it in minutes.

## Roadmap

1. **Citation repair:** prefer graph-edge citations, drop unsupported source IDs,
   and add a deterministic citation validator after synthesis.
2. **Latency:** cache exact-name lookups, parallelize more retrieval branches,
   and test a faster model for synthesis.
3. **Public benchmarks:** add HotpotQA, 2WikiMultiHopQA, and MuSiQue harnesses.
4. **Real Jira/Confluence apps:** complete auth setup, payload parsing, and
   integration tests.
5. **Security pass:** prompt-injection corpus, PII redaction at ingest, and
   access-control regression tests for live-ingested artifacts.
6. **Deployment polish:** one command to run Neo4j, Qdrant, backend, frontend,
   and seed data.
7. **Frontend production pass:** accessibility, responsive layouts, loading and
   error states, and a stable design system.

## Honest Positioning

Strong claim:

> AIM is a graph-backed institutional memory prototype that beats vector-only
> and graph-only baselines on the latest saved fixture for multi-hop NDCG and
> path accuracy.

Do not claim yet:

> AIM is production-ready for arbitrary company data or state-of-the-art across
> public multi-hop benchmarks.

