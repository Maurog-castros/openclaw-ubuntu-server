#!/usr/bin/env bash
set -euo pipefail
ROOT="${OPENCLAW_REPO:-/home/mauro/Dev/openclaw-mauro}"
PY="$ROOT/.venv-linkedin-intel/bin/python"; [[ -x "$PY" ]] || PY="$ROOT/.venv-finanzas/bin/python"; [[ -x "$PY" ]] || PY=python3
exec "$PY" "$ROOT/scripts/jobs_computrabajo_login.py" auto
