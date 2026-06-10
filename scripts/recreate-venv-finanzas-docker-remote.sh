#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/mauro/openclaw-mauro"
CONTAINER="${OPENCLAW_GATEWAY_CONTAINER:-openclaw-openclaw-gateway-1}"

python3 "$ROOT/scripts/apply_openclaw_finanzas_config.py" >/dev/null
cd "$ROOT/openclaw"
docker compose -f docker-compose.yml -f docker-compose.finanzas-mounts.yml up -d openclaw-gateway
sleep 2

docker exec -u root "$CONTAINER" bash -lc '
  set -euo pipefail
  export DEBIAN_FRONTEND=noninteractive
  if ! python3 -m venv /tmp/_venv_test 2>/dev/null; then
    apt-get update -qq
    apt-get install -y -qq python3.11-venv >/dev/null
  else
    rm -rf /tmp/_venv_test
  fi
  VENV=/home/node/openclaw-mauro/.venv-finanzas-docker
  mkdir -p "$VENV"
  find "$VENV" -mindepth 1 -delete 2>/dev/null || true
  python3 -m venv --clear "$VENV"
  "$VENV/bin/pip" install -U pip wheel -q
  "$VENV/bin/pip" install -r /home/node/openclaw-mauro/scripts/requirements-finanzas-agent.txt openai -q
  chown -R node:node "$VENV"
  "$VENV/bin/python" -c "import dotenv, openai; print(\"venv OK\")"
'

docker exec "$CONTAINER" /home/node/openclaw-mauro/scripts/run-finanzas-py.sh /home/node/openclaw-mauro/scripts/finanzas_receipt_whatsapp.py --source whatsapp_foto --json | head -15
echo DONE
