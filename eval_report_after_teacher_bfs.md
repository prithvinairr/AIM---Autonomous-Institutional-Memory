# AIM Benchmark Report (Phase A.2)

## Fixture

- Path: `tests/eval/fixtures/ground_truth.yaml`
- Total items: **34**

| Category | Count |
|---|---:|
| single_hop | 10 |
| multi_hop | 14 |
| negative | 6 |
| ambiguous | 4 |

| Hop depth | Count |
|---:|---:|
| 0 | 6 |
| 1 | 11 |
| 2 | 14 |
| 3 | 2 |
| 4 | 1 |

## Overall

| System | NDCG@10 | Citation | Path Acc | Neg Reject | Likert | p50 Lat (s) |
|---|---:|---:|---:|---:|---:|---:|
| vector_only | 0.344 | 0.485 | 0.000 | 0.833 | 0.000 | 6.187 |
| graph_only | 0.548 | 0.412 | 0.297 | 0.833 | 0.000 | 6.322 |
| aim_full | 0.659 | 0.385 | 0.375 | 0.833 | 0.000 | 29.105 |

## By category

### single_hop

| System | NDCG@10 | Citation | Path Acc | Neg Reject | Likert | p50 Lat (s) |
|---|---:|---:|---:|---:|---:|---:|
| vector_only | 0.334 | 0.400 | 0.000 | 0.000 | — | 6.337 |
| graph_only | 0.592 | 0.200 | 0.000 | 0.000 | — | 4.853 |
| aim_full | 0.851 | 0.200 | 0.100 | 0.000 | — | 24.047 |

### multi_hop

| System | NDCG@10 | Citation | Path Acc | Neg Reject | Likert | p50 Lat (s) |
|---|---:|---:|---:|---:|---:|---:|
| vector_only | 0.460 | 0.393 | 0.000 | 0.000 | — | 7.268 |
| graph_only | 0.799 | 0.500 | 0.720 | 0.000 | — | 8.959 |
| aim_full | 0.836 | 0.363 | 0.839 | 0.000 | — | 30.180 |

### negative

| System | NDCG@10 | Citation | Path Acc | Neg Reject | Likert | p50 Lat (s) |
|---|---:|---:|---:|---:|---:|---:|
| vector_only | 0.000 | 0.667 | 0.000 | 0.833 | — | 5.015 |
| graph_only | 0.000 | 0.833 | 0.000 | 0.833 | — | 4.841 |
| aim_full | 0.000 | 0.833 | 0.000 | 0.833 | — | 23.415 |

### ambiguous

| System | NDCG@10 | Citation | Path Acc | Neg Reject | Likert | p50 Lat (s) |
|---|---:|---:|---:|---:|---:|---:|
| vector_only | 0.479 | 0.750 | 0.000 | 0.000 | — | 6.197 |
| graph_only | 0.385 | 0.000 | 0.000 | 0.000 | — | 5.304 |
| aim_full | 0.547 | 0.250 | 0.000 | 0.000 | — | 30.220 |

## Exit criterion (customer plan A.2)

- Target: `aim_full` beats `vector_only` on multi-hop NDCG by **≥15pp**
  AND ties or wins on single-hop.

- Multi-hop Δ (aim_full − vector_only): **+37.7pp**
- Single-hop Δ (aim_full − vector_only): **+51.7pp**

**Verdict:** `PASS` — AIM full beats vector_only on multi-hop by +37.7pp (≥15pp required) and ties/wins single-hop by +51.7pp.

## Methodology notes

- **NDCG@10**: binary relevance (retrieved id ∈ gold_entities). Logs the
  *right sources were found*; independent of LLM answer quality.
- **Citation**: precision — of what the LLM cited, how much matches
  `gold_sources`; if an item omits `gold_sources`, the harness falls
  back to `gold_entities` so this does not become an abstention score.
- **Path accuracy**: length-normalized LCS of retrieved vs gold graph
  path. 0.0 for vector-only baseline by definition (no graph path).
- **Neg-reject**: keyword check for "I don't know" on negative items.
  Conservative — false positives are caught by the Likert judge.
- **Likert**: 1–5 LLM-judge score on answer fidelity vs `gold_answer`.
  Reported as mean; judge prompt in `aim/eval/judge.py`.
- **Latency**: wall-clock end-to-end per query, p50 over the fixture.
  Measured against the same docker-compose as A.1 — do not compare
  across hardware.
