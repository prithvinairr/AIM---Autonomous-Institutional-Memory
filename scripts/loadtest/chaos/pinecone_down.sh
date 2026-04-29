#!/usr/bin/env bash
# Drill: block Pinecone (iptables DROP to public endpoint) since it's
# not a docker-composed service. Requires root or sudo. On Windows/mac
# dev boxes without iptables, set PINECONE_API_KEY=invalid-key and
# restart the aim container instead — the SDK will 401 and the
# vector_retriever circuit breaker should open.
set -euo pipefail
source "$(dirname "$0")/_common.sh"

require_aim_up
smoke_query "pre" || { echo "[drill] pre-check failed; aborting"; exit 1; }

# Strategy: override PINECONE_API_KEY in the running container so the
# next query gets an auth failure. Docker-compose restart is cleaner
# than network-level blocking and portable across OSes.
echo "[drill] invalidating PINECONE_API_KEY in the aim container..."
CONTAINER=$(docker-compose ps -q aim)
ORIG_KEY=$(docker exec "$CONTAINER" printenv PINECONE_API_KEY || echo "")
docker exec -e PINECONE_API_KEY=invalid-forced-failure "$CONTAINER" \
  sh -c 'echo PINECONE_API_KEY=invalid-forced-failure >> /proc/1/environ' 2>/dev/null || true

# Simpler path: just restart with an override in env. The above env
# mutation doesn't reliably reach the running process — documented
# limitation. Use docker-compose to restart with override:
trap 'docker-compose restart aim >/dev/null && unpause_service aim >/dev/null 2>&1 || true' EXIT

PINECONE_API_KEY=invalid-forced-failure docker-compose up -d aim >/dev/null
sleep 5  # bounded startup wait; /ready polling happens next
require_aim_up

if smoke_query "degraded"; then
  echo "[drill] PASS — graceful degradation (vector results empty, graph+MCP carried)"
  exit 0
else
  echo "[drill] FAIL — AIM did not answer with pinecone unreachable"
  exit 1
fi
