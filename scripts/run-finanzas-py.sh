#!/usr/bin/env bash
# Python finanzas: venv Docker 3.11 primero, luego venv host 3.14.
set -euo pipefail
export PYTHONNOUSERSITE=1
ROOT="/home/node/openclaw-mauro"
if [[ ! -d "$ROOT" ]]; then
  ROOT="/home/mauro/openclaw-mauro"
fi
for PY in "$ROOT/.venv-finanzas-docker/bin/python" "$ROOT/.venv-finanzas/bin/python"; do
  if [[ -x "$PY" ]] && "$PY" -c "import dotenv" 2>/dev/null; then
    exec "$PY" "$@"
  fi
done
exec python3 "$@"
