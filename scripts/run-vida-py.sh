#!/usr/bin/env bash
set -euo pipefail
export PYTHONNOUSERSITE=1
ROOT="/home/node/openclaw-mauro"
if [[ ! -d "$ROOT" ]]; then
  if [[ -d "/home/mauro/Dev/openclaw-mauro" ]]; then
    ROOT="/home/mauro/Dev/openclaw-mauro"
  else
    ROOT="/home/mauro/openclaw-mauro"
  fi
fi
for PY in "$ROOT/.venv-finanzas-docker/bin/python" "$ROOT/.venv-finanzas/bin/python"; do
  if [[ -x "$PY" ]] && "$PY" -c "import dotenv" 2>/dev/null; then
    exec "$PY" "$@"
  fi
done
exec python3 "$@"
