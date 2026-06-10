#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/mauro/openclaw-mauro"
AGENTS="$ROOT/data/config/agents"

echo "[1] apply config (agent id -> fin)..."
python3 "$ROOT/scripts/apply_openclaw_finanzas_config.py" >/dev/null

echo "[2] symlink agents/fin -> finanzas (sesiones/config)..."
cd "$AGENTS"
rm -f fin
ln -sfn finanzas fin

echo "[3] re-aplicar SOUL content delegate..."
python3 "$ROOT/scripts/apply_openclaw_content_config.py" >/dev/null || true

echo "[4] restart gateway..."
cd "$ROOT/openclaw"
docker compose -f docker-compose.yml -f docker-compose.finanzas-mounts.yml up -d openclaw-gateway

echo "[5] verificar agent id..."
grep -E '"id": "fin"|"agentId": "fin"' "$ROOT/data/config/openclaw.json" | head -5
echo "DONE: usa /fin en WhatsApp"
