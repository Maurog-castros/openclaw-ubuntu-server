#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/mauro/Dev/openclaw-mauro"
LOCK="/tmp/openclaw-broh-pulse.lock"
PY="$ROOT/.venv-linkedin-intel/bin/python"
if [ ! -x "$PY" ]; then
  PY="python3"
fi

cd "$ROOT"
flock -n "$LOCK" "$PY" "$ROOT/scripts/broh_pulse.py" --json
