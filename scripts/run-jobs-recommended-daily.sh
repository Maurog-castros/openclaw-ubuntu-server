#!/usr/bin/env bash
# Cron diario: LinkedIn recommended -> CSV. No postula.
set -euo pipefail

ROOT="${OPENCLAW_REPO:-/home/mauro/Dev/openclaw-mauro}"
LOG_DIR="$ROOT/runtime/logs"
LOG_FILE="$LOG_DIR/jobs-recommended-daily.log"
LOCK="/tmp/openclaw-jobs-recommended.lock"
PY="${ROOT}/.venv-linkedin-intel/bin/python"

mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

echo "[$(date -Is)] jobs recommended daily start"

if [[ ! -x "$PY" ]]; then
  PY="${ROOT}/.venv-finanzas/bin/python"
fi
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

flock -n "$LOCK" "$PY" "$ROOT/scripts/jobs_linkedin_recommended.py" --json \
  || echo "[$(date -Is)] jobs recommended daily skipped (lock busy or error)"

echo "[$(date -Is)] jobs recommended daily done"
