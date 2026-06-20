#!/usr/bin/env bash
set -euo pipefail
ROOT="${OPENCLAW_REPO:-/home/mauro/Dev/openclaw-mauro}"
mkdir -p "$ROOT/logs"
exec >>"$ROOT/logs/jobs-chiletrabajos-scrape.log" 2>&1
PY="$ROOT/.venv-linkedin-intel/bin/python"; [[ -x "$PY" ]] || PY="$ROOT/.venv-finanzas/bin/python"; [[ -x "$PY" ]] || PY=python3
echo "[$(date -Is)] chiletrabajos scrape start"
flock -n /tmp/openclaw-jobs-chiletrabajos.lock "$PY" "$ROOT/scripts/jobs_chiletrabajos_scrape.py" --json
echo "[$(date -Is)] chiletrabajos scrape done"
