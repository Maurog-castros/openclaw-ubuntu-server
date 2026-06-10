#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/mauro/openclaw-mauro"
CONTAINER="${OPENCLAW_GATEWAY_CONTAINER:-openclaw-openclaw-gateway-1}"

echo "[1/5] python3.11-venv en gateway..."
docker exec -u root "$CONTAINER" bash -lc '
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3.11-venv python3-pip >/dev/null
'

echo "[2/5] venv finanzas-docker dentro del contenedor..."
docker exec -u root "$CONTAINER" bash -lc '
  set -euo pipefail
  ROOT=/home/node/openclaw-mauro
  VENV="$ROOT/.venv-finanzas-docker"
  rm -rf "$VENV"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -U pip wheel -q
  "$VENV/bin/pip" install -r "$ROOT/scripts/requirements-finanzas-agent.txt" openai -q
  chown -R node:node "$VENV"
  "$VENV/bin/python" -c "import dotenv, openai; print(\"venv OK\")"
'

echo "[3/5] wrapper contenedor..."
docker exec openclaw-openclaw-gateway-1 /home/node/openclaw-mauro/scripts/run-finanzas-py.sh -c "import dotenv, openai; print('wrapper OK')"

echo "[4/5] apply finanzas config..."
python3 "$ROOT/scripts/apply_openclaw_finanzas_config.py"

echo "[5/5] reset sesion finanzas..."
bash "$ROOT/scripts/reset_finanzas_whatsapp_session.sh"

echo "Reiniciando gateway..."
cd "$ROOT/openclaw"
docker compose -f docker-compose.yml -f docker-compose.finanzas-mounts.yml up -d openclaw-gateway

echo "Test receipt..."
docker exec openclaw-openclaw-gateway-1 /home/node/openclaw-mauro/scripts/finanzas_delegate.py --text "boleta" --has-media --json | head -20

echo "DONE"
