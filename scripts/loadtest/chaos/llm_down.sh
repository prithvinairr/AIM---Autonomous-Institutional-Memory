#!/usr/bin/env bash
# Drill: verify the sovereignty-fallback-to-local path fires when the
# external LLM is unreachable AND sovereignty_mode=strict.
#
# Two flavors — test the one matching your deployment:
#   A) llm_provider=anthropic + sovereignty_fallback_to_local=true
#      → simulate Anthropic outage by invalidating the API key; local
#        Ollama must catch the query.
#   B) llm_provider=local (default since δ.2)
#      → simulate Ollama outage by pointing LLM_BASE_URL at :1 (closed
#        port); verify AIM returns 503 (not 500) with a clear error.
#
# The plan's exit criterion: either sovereignty_mode=strict reroutes to
# local (flavor A), or AIM fails loud with a structured 503 (flavor B).
# A silent 500 is a failure.
set -euo pipefail
source "$(dirname "$0")/_common.sh"

require_aim_up
smoke_query "pre" || { echo "[drill] pre-check failed; aborting"; exit 1; }

# Default in current config is llm_provider=local → flavor B.
# Flip LLM_BASE_URL to a closed port and restart the container.
echo "[drill] pointing LLM_BASE_URL at an unreachable port..."
LLM_BASE_URL="http://localhost:1/v1" docker-compose up -d aim >/dev/null
trap 'docker-compose restart aim >/dev/null' EXIT
sleep 5
require_aim_up

# Issue a query. Expected outcomes:
#   - 503 with "llm_unavailable" or similar in error body = PASS
#   - 200 with degraded answer (if some cache or fallback caught it) = PASS
#   - 500 with stack trace = FAIL (we leaked an uncaught exception)
echo "[drill] running degraded query..."
code=$(curl -sS -m 30 -o /tmp/aim_chaos_resp.json -w '%{http_code}' \
  -X POST "${BASE}/api/v1/query" \
  -H "Content-Type: application/json" \
  ${AIM_API_KEY:+-H "X-API-Key: $AIM_API_KEY"} \
  -d '{"query":"Who owns the authentication service?"}' || echo "000")

if [[ "$code" == "200" ]]; then
  echo "[drill] PASS — query answered despite LLM outage (cache or fallback)"
  exit 0
elif [[ "$code" == "503" ]]; then
  echo "[drill] PASS — LLM outage surfaced as structured 503 (fail-loud, not silent)"
  exit 0
else
  echo "[drill] FAIL — LLM outage produced $code (expected 200 or 503)"
  cat /tmp/aim_chaos_resp.json | head -40
  exit 1
fi
