# AIM – Autonomous Institutional Memory

Graph-backed agentic RAG system. FastAPI + LangGraph + Neo4j + Pinecone + Redis + Claude.

## Architecture

```
Request → FastAPI → LangGraph Agent → [decomposer → graph_searcher → vector_retriever → mcp_fetcher → synthesizer]
                                                                     ↓
                                                          Redis (cache + conversations)
```

**Single-worker constraint**: The compiled LangGraph graph and in-process token buckets are module-level singletons. Run one worker per process; scale horizontally behind a load balancer.

## Running locally

```bash
# Install deps
pip install -e ".[dev]"

# Required env (see .env.example)
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
NEO4J_PASSWORD=...
PINECONE_API_KEY=...

# Start
uvicorn aim.main:app --reload --workers 1

# Tests
pytest
pytest tests/unit/
pytest tests/integration/
```

## Key environment variables

| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `development` | `development` / `staging` / `production` |
| `DEBUG` | `false` | Enables docs UI and CORS wildcard |
| `API_KEYS` | `` | Comma-separated. Empty = open (dev mode) |
| `RATE_LIMIT_PER_MINUTE` | `60` | Redis sliding-window; falls back to per-process bucket |
| `CORS_ORIGINS` | `` | Comma-separated. Empty + debug = `*`; empty + prod = locked |
| `REDIS_URL` | `redis://localhost:6379` | Shared by cache and conversation store |
| `CONVERSATION_MAX_TURNS` | `10` | Past turns injected into LLM context |
| `CONVERSATION_TTL_SECONDS` | `604800` | 7 days |
| `FEEDBACK_TTL_SECONDS` | `7776000` | 90 days |
| `LLM_MODEL` | `claude-opus-4-6` | |
| `GRAPH_SEARCH_DEPTH` | `2` | Hops; DEEP mode doubles it (capped at 5) |
| `WEB_CONCURRENCY` | `1` | Must stay 1; app crashes fast if > 1 |

## API surface

```
POST   /api/v1/query                   # standard JSON query
POST   /api/v1/query/stream            # SSE streaming query
GET    /api/v1/conversations           # list threads (?limit=20&offset=0)
GET    /api/v1/conversations/{id}      # full thread
DELETE /api/v1/conversations/{id}      # idempotent delete
POST   /api/v1/feedback                # submit turn feedback
GET    /api/v1/graph/entities          # graph entity search
GET    /health                         # liveness
GET    /ready                          # readiness (Neo4j + Redis + Pinecone + MCP)
GET    /metrics                        # Prometheus scrape endpoint
GET    /circuits                       # circuit breaker status
```

Auth: `X-API-Key: <key>` header. Returns `401` without it (when keys are configured).

## LangGraph agent nodes

1. **decomposer** — Rewrites query into sub-queries, injects conversation history
2. **graph_searcher** — Neo4j neighbourhood traversal (depth/limit varies by `reasoning_depth`)
3. **vector_retriever** — Pinecone ANN search, tracks embedding token usage
4. **mcp_fetcher** — Slack/Jira MCP context (optional, skipped if credentials absent)
5. **synthesizer** — Claude grounded answer with source attribution and cost calculation

### Reasoning depth behaviour

| Depth | Graph hops | Graph limit | Sub-queries | Vector top-k |
|---|---|---|---|---|
| `shallow` | 1 | 5 | First only | 5 |
| `standard` | config (2) | 20 | All | 10 |
| `deep` | min(config×2, 5) | 40 | All | 20 |

## Redis key schema

```
aim:conv:{thread_id}           JSON ConversationThread (TTL = conversation_ttl_seconds)
aim:user_threads:{key_hash}    JSON list of thread summaries per API key (same TTL)
aim:{cache_key}                Response cache entries
aim:rl:{key_hash}              Rate-limit sorted set (sliding window, TTL = 61s)
aim:feedback:{query_id}        Feedback entry (TTL = feedback_ttl_seconds)
```

## Thread ownership

Threads carry `api_key_hash` (SHA-256 hash truncated to 32 hex chars = 128 bits). All ownership checks (`GET /conversations/{id}`, `DELETE /conversations/{id}`, `GET /query/{id}`, `GET /query/{id}/feedback`) use constant-time `hmac.compare_digest` against the caller's hash. `list_threads` only returns threads indexed under the caller's key hash — no cross-key leakage.

## Cost tracking

Every query response includes `cost_info`:
```json
{
  "input_tokens": 1200,
  "output_tokens": 450,
  "embedding_tokens": 320,
  "estimated_usd": 0.018
}
```

Prometheus counters: `aim_tokens_input_total`, `aim_tokens_output_total`, `aim_tokens_embedding_total`, `aim_cost_usd_total`.

## Testing

```bash
pytest tests/unit/           # fakeredis, no external services
pytest tests/integration/    # httpx AsyncClient + mocked stores
pytest --cov=aim             # coverage (≥ 85% required)
```

**Do not mock the database in unit tests for the store** — use `fakeredis`. Integration tests mock at the store level (not Redis) since they test HTTP contracts.

## IDE false positives

The IDE uses the system Python 3.13 install which lacks virtual-env deps. "Cannot find module `fastapi`" warnings are always false positives — they don't affect runtime or tests.

## Production checklist

- [ ] Set `APP_ENV=production` (disables `/docs`, `/redoc`, `/openapi.json`)
- [ ] Set `API_KEYS` to non-empty list
- [ ] Set `CORS_ORIGINS` explicitly (e.g. `https://app.yourcompany.com`)
- [ ] Set `DEBUG=false`
- [ ] Confirm `WEB_CONCURRENCY=1` (or use single-worker container)
- [ ] Set `OTLP_ENDPOINT` if using distributed tracing
- [ ] Verify Redis is reachable (rate limiting + conversations degrade gracefully if not)

## graphify

This project has a graphify knowledge graph at graphify-out/.

## Context Navigation
1. ALWAYS query the knowledge graph first
2. Only read raw files if I explicitly say so
3. Use graphify-out/wiki/index.md

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
