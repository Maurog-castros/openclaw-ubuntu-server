#!/usr/bin/env bash
set -euo pipefail
ROOT="${OPENCLAW_REPO:-/home/mauro/Dev/openclaw-mauro}"
mkdir -p "$ROOT/runtime/logs"
exec >>"$ROOT/runtime/logs/jobs-recommended-analysis.log" 2>&1
PY="$ROOT/.venv-linkedin-intel/bin/python"; [[ -x "$PY" ]] || PY=python3
echo "[$(date -Is)] analysis start"
flock -n /tmp/openclaw-jobs-analysis.lock "$PY" "$ROOT/scripts/jobs_recommended_pipeline.py" --json
echo "[$(date -Is)] analysis done"
