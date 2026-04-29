# AIM Benchmarks

Source report: [`eval_report_after_teacher_bfs.md`](eval_report_after_teacher_bfs.md)

Benchmark command:

```bash
PYTHONIOENCODING=utf-8 python scripts/eval_live.py --out eval_report.md
```

Fixture:

- `tests/eval/fixtures/ground_truth.yaml`
- 34 total items
- 10 single-hop
- 14 multi-hop
- 6 negative controls
- 4 ambiguous queries

Baselines:

- `vector_only`: classic vector RAG.
- `graph_only`: graph BFS from extracted seed entities.
- `aim_full`: AIM's full graph + vector + agentic synthesis pipeline.

## Headline

AIM passes the A.2 customer gate and beats graph-only on the latest saved run
for the core retrieval/path metrics:

- Multi-hop NDCG@10: **0.836** AIM vs **0.799** graph-only.
- Multi-hop path accuracy: **0.839** AIM vs **0.720** graph-only.
- Overall NDCG@10: **0.659** AIM vs **0.548** graph-only.
- Multi-hop delta vs vector-only: **+37.7pp**.

The honest caveat: graph-only is still better on citation precision and much
faster. AIM is stronger on multi-hop retrieval/path structure; it is not yet a
clean sweep.

## Overall

| System | NDCG@10 | Citation | Path Acc | Neg Reject | p50 Latency |
|---|---:|---:|---:|---:|---:|
| `vector_only` | 0.344 | 0.485 | 0.000 | 0.833 | 6.187s |
| `graph_only` | 0.548 | 0.412 | 0.297 | 0.833 | 6.322s |
| **`aim_full`** | **0.659** | 0.385 | **0.375** | 0.833 | 29.105s |

## Multi-Hop

| System | NDCG@10 | Citation | Path Acc | p50 Latency |
|---|---:|---:|---:|---:|
| `vector_only` | 0.460 | 0.393 | 0.000 | 7.268s |
| `graph_only` | 0.799 | **0.500** | 0.720 | **8.959s** |
| **`aim_full`** | **0.836** | 0.363 | **0.839** | 30.180s |

Interpretation:

- AIM finds the right multi-hop evidence slightly better than pure graph BFS.
- AIM reconstructs the right path materially better than graph-only.
- The local synthesizer is not citation-elite yet.
- Latency is dominated by local LLM synthesis, not graph traversal.

## Single-Hop

| System | NDCG@10 | Citation | Path Acc | p50 Latency |
|---|---:|---:|---:|---:|
| `vector_only` | 0.334 | 0.400 | 0.000 | 6.337s |
| `graph_only` | 0.592 | 0.200 | 0.000 | 4.853s |
| **`aim_full`** | **0.851** | 0.200 | **0.100** | 24.047s |

Single-hop stayed strong while multi-hop recall improved. That matters because
many graph-RAG upgrades help long chains but damage simple lookups.

## Negative Controls

| System | NDCG@10 | Citation | Neg Reject |
|---|---:|---:|---:|
| `vector_only` | 0.000 | 0.667 | 0.833 |
| `graph_only` | 0.000 | 0.833 | 0.833 |
| **`aim_full`** | 0.000 | 0.833 | 0.833 |

Negative rejection is 5/6. AIM now also has an exact-incident guardrail: if a
specific incident exists but the requested edge is missing, it says the graph
does not contain that fact instead of inferring from nearby incidents.

## Ambiguous Queries

| System | NDCG@10 | Citation |
|---|---:|---:|
| `vector_only` | 0.479 | 0.750 |
| `graph_only` | 0.385 | 0.000 |
| **`aim_full`** | **0.547** | 0.250 |

Ambiguous queries remain noisy. This is expected: if the user does not anchor
the question clearly, graph traversal cannot fully repair intent.

## Methodology

- **NDCG@10:** binary relevance over retrieved IDs against `gold_entities`.
- **Citation:** precision of cited IDs against gold sources/entities.
- **Path accuracy:** normalized longest-common-subsequence over retrieved path
  IDs versus the gold graph path.
- **Neg reject:** whether the system refuses when the fixture says the answer
  is absent.
- **Latency:** wall-clock p50 over the fixture.

## Reproducibility Notes

The fixture is small. Treat these numbers as an engineering smoke test, not a
published benchmark. Earlier runs varied by a few points depending on local
model behavior, retrieval ordering, and branch settings. The latest saved run is
the one reported here because it reflects the current teacher-BFS retrieval
configuration.

Next benchmark targets:

- HotpotQA
- 2WikiMultiHopQA
- MuSiQue
- larger internal fixture with `gold_sources` filled for every item

