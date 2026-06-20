#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/mauro/openclaw-mauro"
TS="$(date +%F_%H%M%S)"
LOGS_DIR="$ROOT/runtime/logs"
LOG_FILE="$LOGS_DIR/intel-daily-radar-${TS}.log"
COMPOSE_FILE="$ROOT/openclaw/docker-compose.yml"
COMPOSE_FINANZAS="$ROOT/openclaw/docker-compose.finanzas-mounts.yml"

mkdir -p "$LOGS_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[$(date -Is)] Starting Intel daily radar grouped WhatsApp"

docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_FINANZAS" \
  --project-directory "$ROOT/openclaw" \
  exec -T openclaw-gateway \
  /home/node/openclaw-mauro/.venv-finanzas/bin/python \
  /home/node/openclaw-mauro/scripts/intel_daily_messages.py \
  --refresh \
  --send-whatsapp \
  --json

echo "[$(date -Is)] Completed Intel daily radar grouped WhatsApp"
