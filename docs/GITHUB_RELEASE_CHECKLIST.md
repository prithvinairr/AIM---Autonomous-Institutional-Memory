# GitHub Release Checklist

Use this before making the repository public.

## Secrets

- [ ] `.env` is not committed.
- [ ] `frontend/.env.local` is not committed.
- [ ] Slack bot/app/signing secrets have been rotated if they appeared in demos.
- [ ] Neo4j demo password is not reused anywhere important.
- [ ] Cloudflare tunnel URLs in screenshots or docs are expired or non-sensitive.

## Proof

- [ ] README screenshots render from `docs/images/`.
- [ ] `BENCHMARKS.md` matches the latest report you want to present.
- [ ] `LIMITATIONS.md` is committed and visible.
- [ ] `SECURITY.md` is committed and visible.
- [ ] `eval_report_after_teacher_bfs.md` and `.json` remain in the repo as evidence.

## Sanity Commands

```bash
pytest
cd frontend && npm run typecheck && npm test
PYTHONIOENCODING=utf-8 python scripts/eval_live.py --out eval_report.md
```

## Suggested GitHub Description

Graph-backed institutional memory engine with live Slack ingest, Neo4j GraphRAG,
provenance-aware answers, local-first inference, and benchmarked multi-hop
retrieval.

## Suggested CV Bullet

Built AIM, a local-first graph-backed institutional memory engine with live
Slack ingestion, Neo4j GraphRAG retrieval, provenance-aware answers, streaming
Next.js frontend, and benchmarked multi-hop reasoning. Latest saved fixture:
0.836 multi-hop NDCG@10 vs 0.799 graph-only, and 0.839 path accuracy vs 0.720
graph-only.

