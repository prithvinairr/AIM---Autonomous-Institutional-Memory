#!/usr/bin/env bash
# Drill: kill Neo4j, verify AIM still answers from vector + MCP.
# Exit 0 = graceful degradation; exit 1 = hard failure.
set -euo pipefail
source "$(dirname "$0")/_common.sh"

require_aim_up
echo "[drill] warmup"
smoke_query "pre" || { echo "[drill] pre-check failed; aborting"; exit 1; }

pause_service neo4j
trap 'unpause_service neo4j' EXIT

echo "[drill] running degraded query..."
if smoke_query "degraded"; then
  echo "[drill] PASS — graceful degradation (graph empty, answer still landed)"
  exit 0
else
  echo "[drill] FAIL — AIM did not answer with neo4j down"
  exit 1
fi
