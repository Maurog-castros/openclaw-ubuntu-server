#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/mauro/openclaw-mauro"
PY="$ROOT/.venv-finanzas/bin/python"
LOG="$ROOT/logs/intel-consolidated-cron.log"
mkdir -p "$ROOT/logs"
exec >>"$LOG" 2>&1
echo "[$(date -Is)] intel consolidated refresh"
flock -n /tmp/openclaw-intel-consolidated.lock "$PY" "$ROOT/scripts/intel_consolidated_report.py" --refresh --json
echo "[$(date -Is)] done"
