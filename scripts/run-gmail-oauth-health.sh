#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/mauro/Dev/openclaw-mauro"
PY="$ROOT/.venv-finanzas/bin/python"
exec flock -n /tmp/openclaw-gmail-oauth-health.lock \
  "$PY" "$ROOT/scripts/gmail_oauth_health.py" --json \
  >> "$ROOT/logs/gmail-oauth-health.log" 2>&1
