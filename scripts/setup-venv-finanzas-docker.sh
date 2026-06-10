#!/usr/bin/env bash
# Crea .venv-finanzas-docker con Python 3.11 del contenedor gateway (compatible exec in-container).
set -euo pipefail
ROOT="${OPENCLAW_REPO:-/home/mauro/openclaw-mauro}"
VENV="$ROOT/.venv-finanzas-docker"
COMPOSE="$ROOT/openclaw/docker-compose.yml"
COMPOSE_FIN="$ROOT/openclaw/docker-compose.finanzas-mounts.yml"
CONTAINER="${OPENCLAW_GATEWAY_CONTAINER:-openclaw-openclaw-gateway-1}"

echo "[1/3] Creando venv en $VENV (via contenedor)..."
docker exec "$CONTAINER" bash -lc "
  set -euo pipefail
  ROOT=/home/node/openclaw-mauro
  VENV=\"\$ROOT/.venv-finanzas-docker\"
  rm -rf \"\$VENV\"
  python3 -m venv \"\$VENV\"
  \"\$VENV/bin/pip\" install -U pip wheel -q
  \"\$VENV/bin/pip\" install -r \"\$ROOT/scripts/requirements-finanzas-agent.txt\" openai -q
  \"\$VENV/bin/python\" -c 'import dotenv, openai; print(\"venv finanzas-docker OK\")'
"

echo "[2/3] Verificando run-finanzas-py.sh..."
chmod +x "$ROOT/scripts/run-finanzas-py.sh"
"$ROOT/scripts/run-finanzas-py.sh" -c "import dotenv; print('wrapper OK')"

echo "[3/3] Listo. Reinicia gateway si cambiaste docker-compose.finanzas-mounts.yml"
