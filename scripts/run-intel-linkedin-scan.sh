#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/mauro/openclaw-mauro"
VENV="$ROOT/.venv-linkedin-intel"
PY="$VENV/bin/python"
LOG="$ROOT/logs/intel-linkedin-scan.log"
mkdir -p "$ROOT/logs"
exec >>"$LOG" 2>&1
echo "[$(date -Is)] intel linkedin scan start"
flock -n /tmp/openclaw-intel-linkedin.lock "$PY" "$ROOT/scripts/linkedin_intel_scout.py" scan --json
echo "[$(date -Is)] intel linkedin scan done"
