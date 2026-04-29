"""A.1 memory leak harness.

Issues N queries back-to-back against a running AIM instance and records
RSS every K queries. If RSS grows unboundedly, there's a leak.

Doesn't try to be clever about GC or tcmalloc fragmentation — just
measures the OS-reported RSS and plots it. A real leak shows up as a
monotonic upward line; normal steady-state shows bounded oscillation.

Usage:
    export AIM_BASE_URL=http://localhost:8000
    export AIM_API_KEY=...  # optional
    python scripts/loadtest/memory_leak.py --queries 10000 --sample-every 500

Output:
    scripts/loadtest/memory_leak.csv  — rows of (query_n, rss_mb, elapsed_s)
    scripts/loadtest/memory_leak.txt  — terminal-plottable summary

Exit criteria (you decide based on your SLO):
    * Typical: RSS increases by <50 MB over 10k queries once warm.
    * Unacceptable: monotonic growth exceeding 10 MB per 1k queries
      after the first 2k (warmup window).
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import httpx

# Same query mix as loadtest.js so warmup/cache behaviour matches.
SINGLE = [
    "Who owns the authentication service?",
    "Who is the tech lead for Project Aurora?",
    "What does the svc-gateway do?",
]
MULTI = [
    "Why did we migrate off Kafka and who approved it?",
    "Which incidents in 2025 involved both svc-auth and the Platform team?",
]
NEGATIVE = ["Tell me about Project Zorg."]


def pick_query() -> str:
    r = random.random()
    if r < 0.50:
        return random.choice(SINGLE)
    if r < 0.85:
        return random.choice(MULTI)
    return random.choice(NEGATIVE)


def rss_mb_of(container: str) -> float:
    """RSS in MB of the given docker container, via `docker stats --no-stream`.

    Falls back to 0.0 on parse failure rather than crashing the run —
    a missing sample is preferable to losing the whole series.
    """
    try:
        out = subprocess.check_output(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container],
            timeout=5,
        ).decode().strip()
        # Format like "512.3MiB / 2GiB" — we want the first number.
        used = out.split("/")[0].strip()
        # Handle MiB/GiB/KiB
        mult = {"KiB": 1/1024, "MiB": 1, "GiB": 1024}
        for unit, factor in mult.items():
            if used.endswith(unit):
                return float(used[: -len(unit)]) * factor
        return 0.0
    except Exception:
        return 0.0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--queries", type=int, default=10_000)
    p.add_argument("--sample-every", type=int, default=500)
    p.add_argument("--container", default="aim-aim-1",
                   help="Docker container name for RSS sampling. "
                        "Adjust for your docker-compose project name.")
    p.add_argument("--base", default=os.environ.get("AIM_BASE_URL", "http://localhost:8000"))
    p.add_argument("--api-key", default=os.environ.get("AIM_API_KEY", ""))
    p.add_argument("--out", type=Path, default=Path("scripts/loadtest/memory_leak.csv"))
    args = p.parse_args()

    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["X-API-Key"] = args.api_key

    args.out.parent.mkdir(parents=True, exist_ok=True)
    csv_f = args.out.open("w", newline="")
    writer = csv.writer(csv_f)
    writer.writerow(["query_n", "rss_mb", "elapsed_s", "http_code"])

    t_start = time.time()
    # 15s timeout matches the node_timeout default; beyond this the
    # request has other problems and we shouldn't conflate with leaks.
    client = httpx.Client(base_url=args.base, timeout=15.0, headers=headers)

    print(f"[leak] issuing {args.queries} queries, sampling RSS every {args.sample_every}")
    print(f"[leak] RSS sampled from docker container: {args.container}")

    initial_rss = rss_mb_of(args.container)
    print(f"[leak] initial RSS: {initial_rss:.1f} MB")

    for n in range(1, args.queries + 1):
        try:
            resp = client.post("/api/v1/query",
                               json={"query": pick_query(), "reasoning_depth": "standard"})
            code = resp.status_code
        except httpx.HTTPError as e:
            code = -1
            print(f"[leak] n={n} http error: {e}")

        if n % args.sample_every == 0:
            rss = rss_mb_of(args.container)
            elapsed = time.time() - t_start
            writer.writerow([n, f"{rss:.1f}", f"{elapsed:.1f}", code])
            csv_f.flush()
            # Diff vs initial so the operator can eyeball growth inline.
            print(f"[leak] n={n:>6}  rss={rss:6.1f} MB  Δ={rss-initial_rss:+6.1f} MB  elapsed={elapsed:6.1f}s")

    csv_f.close()
    final_rss = rss_mb_of(args.container)
    total_growth = final_rss - initial_rss
    per_1k = (total_growth / args.queries) * 1000

    summary = Path(args.out).with_suffix(".txt")
    summary.write_text(
        f"AIM A.1 Memory Leak Harness\n"
        f"queries={args.queries} sample_every={args.sample_every}\n"
        f"initial_rss_mb={initial_rss:.1f}\n"
        f"final_rss_mb={final_rss:.1f}\n"
        f"total_growth_mb={total_growth:+.1f}\n"
        f"growth_per_1k_queries_mb={per_1k:+.2f}\n"
        f"exit_criterion (<10 MB / 1k queries post-warmup): "
        f"{'PASS' if per_1k < 10 else 'REVIEW'}\n"
    )
    print(summary.read_text())
    return 0 if per_1k < 10 else 1


if __name__ == "__main__":
    sys.exit(main())
