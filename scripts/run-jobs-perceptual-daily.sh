#!/usr/bin/env bash
set -euo pipefail
ROOT="${OPENCLAW_REPO:-/home/mauro/Dev/openclaw-mauro}"
mkdir -p "$ROOT/runtime/logs"
exec >>"$ROOT/runtime/logs/jobs-perceptual-scrape.log" 2>&1
PY="$ROOT/.venv-linkedin-intel/bin/python"; [[ -x "$PY" ]] || PY="$ROOT/.venv-finanzas/bin/python"; [[ -x "$PY" ]] || PY=python3
echo "[$(date -Is)] perceptual scrape start"
flock -n /tmp/openclaw-jobs-perceptual.lock "$PY" "$ROOT/scripts/jobs_perceptual_scrape.py" --json \
  || echo "[$(date -Is)] perceptual scrape skipped (lock busy or error)"
echo "[$(date -Is)] perceptual scrape done"
