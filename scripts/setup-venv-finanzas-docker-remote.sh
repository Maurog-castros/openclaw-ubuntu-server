#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/mauro/openclaw-mauro"
VENV="$ROOT/.venv-finanzas-docker"

echo "[1/4] venv Python 3.11 via imagen docker..."
docker run --rm -v "$ROOT:/repo" python:3.11-slim-bookworm bash -lc '
  set -euo pipefail
  rm -rf /repo/.venv-finanzas-docker
  python -m venv /repo/.venv-finanzas-docker
  /repo/.venv-finanzas-docker/bin/pip install -U pip wheel -q
  /repo/.venv-finanzas-docker/bin/pip install -r /repo/scripts/requirements-finanzas-agent.txt openai -q
  /repo/.venv-finanzas-docker/bin/python -c "import dotenv, openai; print(\"venv finanzas-docker OK\")"
'

echo "[2/4] wrapper host..."
chmod +x "$ROOT/scripts/run-finanzas-py.sh"
"$ROOT/scripts/run-finanzas-py.sh" -c "import dotenv; print('wrapper host OK')"

echo "[3/4] wrapper contenedor..."
docker exec openclaw-openclaw-gateway-1 /home/node/openclaw-mauro/scripts/run-finanzas-py.sh -c "import dotenv; print('wrapper container OK')"

echo "[4/4] finanzas_receipt test..."
docker exec openclaw-openclaw-gateway-1 /home/node/openclaw-mauro/scripts/run-finanzas-py.sh /home/node/openclaw-mauro/scripts/finanzas_receipt_whatsapp.py --source whatsapp_foto --json 2>&1 | head -20

echo "DONE"
