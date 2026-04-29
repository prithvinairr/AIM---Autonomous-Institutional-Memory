# Chaos drills — A.1 degradation matrix

Each script below kills **one** dependency and re-runs a smoke test.
The exit criterion for A.1 chaos is that AIM degrades gracefully:
it returns a response (possibly with reduced confidence) rather
than 500-ing. If a dependency kill produces 500s, that's a bug.

**Never run two of these simultaneously** — the plan is explicit that
single-point chaos gives interpretable results; multi-point chaos
gives noise.

Run against `docker-compose up -d` and a warmed cache (one or two
queries first so Redis is populated).

## Quickstart

```bash
# Terminal 1: bring the stack up
docker-compose up -d

# Terminal 2: wait for ready, then run each drill
./scripts/loadtest/chaos/neo4j_down.sh
./scripts/loadtest/chaos/redis_down.sh
./scripts/loadtest/chaos/pinecone_down.sh
./scripts/loadtest/chaos/llm_down.sh
```

## Expected behaviours

| Drill | Expected graceful degradation |
|---|---|
| `neo4j_down` | `/ready` reports neo4j:down. Queries return but graph_searcher contributes zero hits; confidence drops. |
| `redis_down` | Rate limiter falls back to in-process bucket (see `aim/api/middleware/rate_limit.py`). Conversations do not persist across requests. Queries still answer. |
| `pinecone_down` | vector_retriever returns empty list; answer is synthesized from graph + MCP only. Provenance has zero vector sources. |
| `llm_down` | If `sovereignty_mode=strict` and `llm_provider=anthropic`: local Ollama fallback fires. If pure local: test that the local endpoint is reachable; else fail honestly. |

If any drill returns **500** instead of a degraded 200, that's the A.1
gate failing — fix before proceeding to A.2.
