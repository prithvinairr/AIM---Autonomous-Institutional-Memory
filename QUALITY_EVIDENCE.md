# AIM 9.5 Evidence Snapshot

Generated from local verification on 2026-04-25.

## Passing Gates

| Gate | Command | Result |
|---|---|---|
| Backend unit + eval suite | `python -m pytest -p no:cacheprovider tests/unit tests/eval -q` | Passed, 1034 collected, 1 skipped |
| Fatal Python lint | `python -m ruff check aim tests --select=E9,F63,F7,F82` | Passed |
| Frontend typecheck | `npm run typecheck` | Passed |
| Frontend unit tests | `npm test -- --run` | Passed, 79 tests |
| Changed Python compile check | `python -m compileall -q ...` | Passed |

## Architecture Evidence

- GraphRAG is active: graph hybrid search and path finding are wired through
  `aim/agents/nodes/graph_searcher.py` and `aim/graph/neo4j_client.py`.
- Multi-hop reasoning is active: missing-hop detection, evaluator penalties,
  branch-and-select configuration, and hop-depth eval fixtures are present.
- Causal lineage is active: the API provenance includes graph nodes, graph
  edges, temporal chains, institutional facts, source artifacts, support IDs,
  and violation edge IDs.
- Frontend provenance visualization is active: `frontend/lib/provenance-map.ts`
  converts real `ProvenanceMap` data into cited nebula nodes and directed,
  confidence-bearing, color-coded lineage edges.
- Seed data now has cross-domain proof: healthcare fixture covers
  `Patient -> Study -> Treatment -> Outcome`, and the eval fixture includes
  explicit `hop_depth` labels through 4-hop cases.
- Scale proof is available: `aim/scripts/seed_domains.py` generates a
  deterministic 10k-node volume fixture.
- CI proof gates are wired in `.github/workflows/ci.yml`.

## Known Gaps

- The A.2 live benchmark is not closed yet. The current fixture contains
  34 items, not the earlier 31: 10 single-hop, 14 multi-hop, 6 negative,
  and 4 ambiguous. The empirical "extraordinary" gate is `aim_full` beating
  `vector_only` by at least +15 percentage points on live multi-hop NDCG
  while tying or winning single-hop.
- Docker is required to close that gate locally. The current machine has the
  Docker client installed, but the daemon is not reachable at
  `npipe:////./pipe/docker_engine`, so the seeded stack cannot be started yet.
- Full strict `mypy aim` is not yet green; it reports existing typing debt
  across MCP, LLM providers, cache, and synthesizer modules.
- Full broad `ruff check aim tests` is not yet green; fatal lint is green, but
  style/import/line-length cleanup remains.
- Playwright seeded-stack E2E, axe, and Lighthouse are not yet installed or run.
- `graphify` rebuild is still blocked locally because the `graphify` Python
  module is not installed.
