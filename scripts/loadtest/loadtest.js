// AIM load test — Phase A.1 of the customer-ready plan.
//
// Three stages land in a single run so the RPS curve shape is legible
// without re-invoking k6 three times:
//
//   1. baseline  (1× expected QPS, warms caches, gives reference p99)
//   2. headroom  (5× — does quality hold when things are busy?)
//   3. break     (10× — where does it actually fall over?)
//
// Each stage is long enough that the sliding-window rate limiter and the
// Redis-backed cache reach steady state; shorter runs measure startup
// cost, not operating cost.
//
// Query mix is 3 shapes:
//   * single-hop ("Who owns service X?")     — cheap, mostly graph+vector
//   * multi-hop  ("Why did we move off Kafka?") — hits decomposer + reloop
//   * negative   ("Tell me about Project Zorg") — no corpus hits, full pipeline
// The mix is 50/35/15 — roughly what a real operator would see, weighted
// toward the cheap path so a break in multi-hop doesn't mask a break in
// the cheap path.
//
// ── Running ────────────────────────────────────────────────────────────
//   export AIM_BASE_URL=http://localhost:8000
//   export AIM_API_KEY=<key>
//   k6 run scripts/loadtest/loadtest.js
//
// ── Reading the output ────────────────────────────────────────────────
// At the end k6 prints a summary block. The two numbers that matter for
// the A.1 exit criterion:
//   http_req_duration p(99) — end-to-end latency, 99th percentile
//   http_req_failed  rate   — error rate; must stay <1% at baseline
// The checks{baseline:true}, checks{headroom:true}, checks{break:true}
// submetrics break it down per stage so you can see where p99 blows up.
//
// The plan's exit criterion lets YOU define acceptable p99 — this script
// just produces the number. Typical for a 2GB-RAM single-worker AIM on
// the default docker-compose: p99 <1.5s at baseline, <4s at headroom.

import http from 'k6/http';
import { check, sleep } from 'k6/check';
import { Trend, Rate } from 'k6/metrics';

const BASE = __ENV.AIM_BASE_URL || 'http://localhost:8000';
const KEY  = __ENV.AIM_API_KEY  || '';

// Custom per-stage metrics — k6 auto-tags via exec.scenario.name.
const queryLatency = new Trend('aim_query_latency_ms');
const queryErrors  = new Rate('aim_query_errors');

// Query corpus chosen to match the seed_demo.py fixture. Single-hop
// names are entities the seed explicitly creates so the cache warms
// predictably; multi-hop questions require decomposer + graph traversal;
// negative questions exercise the empty-retrieval path.
const QUERIES = {
  single: [
    'Who owns the authentication service?',
    'Who is the tech lead for Project Aurora?',
    'What does the svc-gateway do?',
    'Who manages the Platform team?',
    'What runbook covers Kafka lag incidents?',
  ],
  multi: [
    'Why did we migrate off Kafka and who approved it?',
    'Which incidents in 2025 involved both svc-auth and the Platform team?',
    'What ADRs reference INC-2025-012 and who owns their follow-ups?',
    'Trace the decision path from INC-2025-003 to its runbook update.',
    'Who is on-call for services that had incidents referenced by ADR-003?',
  ],
  negative: [
    'Tell me about Project Zorg.',
    'Who owns the Quantum Entanglement service?',
    'What ADR covers the migration to COBOL?',
  ],
};

function pickQuery() {
  const r = Math.random();
  if (r < 0.50)      return [QUERIES.single[Math.floor(Math.random() * QUERIES.single.length)], 'single'];
  else if (r < 0.85) return [QUERIES.multi[Math.floor(Math.random() * QUERIES.multi.length)], 'multi'];
  else               return [QUERIES.negative[Math.floor(Math.random() * QUERIES.negative.length)], 'negative'];
}

export const options = {
  // Three named scenarios run sequentially so stage labels stay clean
  // in the output. Stage duration ≥ rate-limiter window (60s) so the
  // sliding window doesn't skew the tail.
  scenarios: {
    baseline: {
      executor: 'constant-arrival-rate',
      rate: 2,            // 2 QPS baseline
      timeUnit: '1s',
      duration: '2m',
      preAllocatedVUs: 10,
      maxVUs: 20,
      tags: { stage: 'baseline' },
    },
    headroom: {
      executor: 'constant-arrival-rate',
      rate: 10,           // 5× baseline
      timeUnit: '1s',
      duration: '2m',
      preAllocatedVUs: 30,
      maxVUs: 60,
      startTime: '2m30s',
      tags: { stage: 'headroom' },
    },
    breakpoint: {
      executor: 'constant-arrival-rate',
      rate: 20,           // 10× baseline — intentionally above steady-state
      timeUnit: '1s',
      duration: '2m',
      preAllocatedVUs: 60,
      maxVUs: 120,
      startTime: '5m',
      tags: { stage: 'break' },
    },
  },
  thresholds: {
    // These are DIAGNOSTIC, not pass/fail — the exit criterion is whatever
    // YOU decide p99 should be on YOUR corpus. Set to loud-but-generous
    // defaults so the run doesn't abort on a blip.
    'http_req_duration{stage:baseline}': ['p(99)<3000'],
    'http_req_failed{stage:baseline}':    ['rate<0.01'],
    'http_req_failed{stage:headroom}':    ['rate<0.05'],
    // break stage has no threshold — we WANT to see it fall over to
    // learn the shape of the cliff.
  },
};

export default function () {
  const [query, shape] = pickQuery();
  const headers = { 'Content-Type': 'application/json' };
  if (KEY) headers['X-API-Key'] = KEY;

  const t0 = Date.now();
  const res = http.post(
    `${BASE}/api/v1/query`,
    JSON.stringify({ query, reasoning_depth: 'standard' }),
    { headers, timeout: '30s', tags: { shape } },
  );
  const elapsed = Date.now() - t0;

  queryLatency.add(elapsed, { shape });
  queryErrors.add(res.status !== 200, { shape });

  check(res, {
    'status is 200':       (r) => r.status === 200,
    'has answer':          (r) => r.status === 200 && r.json('answer') && r.json('answer').length > 10,
    'has provenance':      (r) => r.status === 200 && r.json('provenance') !== null,
    'has query_id':        (r) => r.status === 200 && r.json('query_id'),
  }, { shape });

  // Tiny jitter so we don't thundering-herd the rate limiter.
  sleep(Math.random() * 0.1);
}

export function handleSummary(data) {
  // Emit a compact markdown block on top of the default k6 output so
  // the A.1 runbook can grep the numbers it cares about.
  const p99 = (name) => data.metrics[name]?.values?.['p(99)']?.toFixed(0) ?? '?';
  const rate = (name) => (data.metrics[name]?.values?.rate * 100).toFixed(2) ?? '?';

  const md = `
## AIM A.1 Load Test Summary

| Stage | p99 latency (ms) | Error rate |
|---|---|---|
| baseline (2 QPS) | ${p99('http_req_duration{stage:baseline}')} | ${rate('http_req_failed{stage:baseline}')}% |
| headroom (10 QPS) | ${p99('http_req_duration{stage:headroom}')} | ${rate('http_req_failed{stage:headroom}')}% |
| breakpoint (20 QPS) | ${p99('http_req_duration{stage:break}')} | ${rate('http_req_failed{stage:break}')}% |

Exit criterion (you define): baseline p99 ≤ your target, baseline error rate <1%.
`;
  return {
    'stdout': md,
    'loadtest_summary.json': JSON.stringify(data, null, 2),
  };
}
