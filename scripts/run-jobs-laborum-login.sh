#!/usr/bin/env bash
set -euo pipefail
ROOT="${OPENCLAW_REPO:-/home/mauro/Dev/openclaw-mauro}"
PY="$ROOT/.venv-jobs-portals/bin/python"
[[ -x "$PY" ]] || PY=python3
exec xvfb-run -a "$PY" "$ROOT/scripts/jobs_laborum_login.py" login --headed "$@"
