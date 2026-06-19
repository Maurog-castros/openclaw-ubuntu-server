#!/usr/bin/env bash
set -euo pipefail
ROOT="${OPENCLAW_REPO:-/home/mauro/Dev/openclaw-mauro}"
mkdir -p "$ROOT/logs"
exec >>"$ROOT/logs/jobs-recommended-report.log" 2>&1
PY="$ROOT/.venv-finanzas/bin/python"; [[ -x "$PY" ]] || PY=python3
echo "[$(date -Is)] report start"
flock -n /tmp/openclaw-jobs-report.lock "$PY" "$ROOT/scripts/jobs_recommended_digest.py" --send-whatsapp --json
echo "[$(date -Is)] report done"
