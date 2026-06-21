#!/usr/bin/env bash
set -euo pipefail
ROOT="${OPENCLAW_REPO:-/home/mauro/Dev/openclaw-mauro}"
mkdir -p "$ROOT/runtime/logs"
exec >>"$ROOT/runtime/logs/jobs-chiletrabajos-scrape.log" 2>&1
PY="$ROOT/.venv-linkedin-intel/bin/python"; [[ -x "$PY" ]] || PY="$ROOT/.venv-finanzas/bin/python"; [[ -x "$PY" ]] || PY=python3
echo "[$(date -Is)] chiletrabajos scrape start"
if ! flock -n /tmp/openclaw-jobs-chiletrabajos.lock "$PY" "$ROOT/scripts/jobs_chiletrabajos_scrape.py" --json; then
  echo "[$(date -Is)] chiletrabajos authenticated scrape failed; retrying public"
  flock -n /tmp/openclaw-jobs-chiletrabajos.lock "$PY" "$ROOT/scripts/jobs_chiletrabajos_scrape.py" --no-session --json
fi
echo "[$(date -Is)] chiletrabajos scrape done"
