#!/usr/bin/env bash
# Shared helpers for A.1 chaos drills.
#
# Every drill:
#   1. Smoke-checks that AIM is up before killing anything.
#   2. Kills ONE dependency (via docker compose pause, not down — pause
#      is faster to reverse and survives a ctrl-C better).
#   3. Issues a smoke query and reports status + answer-length.
#   4. Unpauses and confirms /ready recovers.
#
# Exit codes:
#   0 = degraded gracefully (200 response, answer present)
#   1 = hard failure (500, timeout, or empty answer)
#   2 = setup failure (AIM not reachable before we even started)

set -euo pipefail

BASE="${AIM_BASE_URL:-http://localhost:8000}"
KEY_HDR=""
[[ -n "${AIM_API_KEY:-}" ]] && KEY_HDR="X-API-Key: $AIM_API_KEY"

curl_json() {
  if [[ -n "$KEY_HDR" ]]; then
    curl -sS -m 30 -o /tmp/aim_chaos_resp.json -w '%{http_code}' \
      -H "Content-Type: application/json" -H "$KEY_HDR" "$@"
  else
    curl -sS -m 30 -o /tmp/aim_chaos_resp.json -w '%{http_code}' \
      -H "Content-Type: application/json" "$@"
  fi
}

require_aim_up() {
  local code
  code=$(curl_json "${BASE}/health" || echo "000")
  if [[ "$code" != "200" ]]; then
    echo "[setup] AIM /health did not return 200 (got $code). Start with: docker-compose up -d"
    exit 2
  fi
}

smoke_query() {
  local label="$1"
  local q='{"query":"Who owns the authentication service?","reasoning_depth":"standard"}'
  local code
  code=$(curl_json -X POST "${BASE}/api/v1/query" -d "$q" || echo "000")
  local answer_len
  answer_len=$(python -c 'import json,sys; d=json.load(open("/tmp/aim_chaos_resp.json")); print(len(d.get("answer","")))' 2>/dev/null || echo 0)
  echo "[${label}] http=${code} answer_len=${answer_len}"
  if [[ "$code" == "200" && "$answer_len" -gt 10 ]]; then
    return 0
  fi
  return 1
}

pause_service() {
  local svc="$1"
  echo "[drill] pausing $svc"
  docker-compose pause "$svc" >/dev/null
}

unpause_service() {
  local svc="$1"
  echo "[drill] unpausing $svc"
  docker-compose unpause "$svc" >/dev/null
  # Ready takes a beat to recover after unpause. Not a sleep loop — a
  # bounded wait with a loud timeout.
  for _ in $(seq 1 15); do
    if curl -sS -m 2 "${BASE}/ready" | grep -q '"status":"ok"'; then
      echo "[drill] /ready recovered"
      return 0
    fi
    sleep 1
  done
  echo "[drill] WARNING: /ready did not recover within 15s after unpausing $svc"
  return 1
}
