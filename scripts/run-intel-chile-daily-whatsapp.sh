#!/usr/bin/env bash
# Intel Daily Chile (formato reports/intelligence) → WhatsApp.
set -euo pipefail

ROOT="${OPENCLAW_REPO:-/home/mauro/openclaw-mauro}"
SLOT="${1:-morning}"
LOG_DIR="$ROOT/runtime/logs"
LOG_FILE="$LOG_DIR/intel-chile-daily-${SLOT}.log"
LOCK="/tmp/openclaw-intel-chile-${SLOT}.lock"
PY="${ROOT}/.venv-finanzas/bin/python"

mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

echo "[$(date -Is)] intel chile daily ($SLOT) start"

if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

flock -n "$LOCK" "$PY" "$ROOT/scripts/intel_chile_daily_report.py" \
  --slot "$SLOT" \
  --send-whatsapp \
  --json \
  || echo "[$(date -Is)] intel chile daily ($SLOT) skipped (lock busy or error)"

echo "[$(date -Is)] intel chile daily ($SLOT) done"
