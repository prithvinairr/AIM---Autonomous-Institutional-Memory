#!/usr/bin/env bash
# Drill: kill Redis. Rate limiter must fall back to in-process bucket
# (aim/api/middleware/rate_limit.py); conversations do not persist.
# Query must still answer.
set -euo pipefail
source "$(dirname "$0")/_common.sh"

require_aim_up
smoke_query "pre" || { echo "[drill] pre-check failed; aborting"; exit 1; }

pause_service redis
trap 'unpause_service redis' EXIT

if smoke_query "degraded"; then
  echo "[drill] PASS — graceful degradation (rate limit in-process, cache disabled)"
  exit 0
else
  echo "[drill] FAIL — AIM did not answer with redis down"
  exit 1
fi
