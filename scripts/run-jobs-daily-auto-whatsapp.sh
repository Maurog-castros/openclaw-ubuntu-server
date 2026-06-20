#!/usr/bin/env bash
# Cron diario: buscar vacantes LinkedIn + postular auto (3) + WhatsApp.
set -euo pipefail

ROOT="${OPENCLAW_REPO:-/home/mauro/openclaw-mauro}"
LOG_DIR="$ROOT/runtime/logs"
LOG_FILE="$LOG_DIR/jobs-daily-auto.log"
LOCK="/tmp/openclaw-jobs-daily.lock"
PY="${ROOT}/.venv-finanzas/bin/python"

mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

echo "[$(date -Is)] jobs daily auto start"

if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

flock -n "$LOCK" "$PY" "$ROOT/scripts/jobs_daily_auto.py" --send-whatsapp --json \
  || echo "[$(date -Is)] jobs daily auto skipped (lock busy or error)"

echo "[$(date -Is)] jobs daily auto done"
