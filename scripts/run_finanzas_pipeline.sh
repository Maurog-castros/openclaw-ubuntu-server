#!/usr/bin/env bash
set -euo pipefail
ROOT="${OPENCLAW_ROOT:-/home/mauro/Dev/openclaw-mauro}"
if [[ ! -d "$ROOT" ]]; then
  ROOT="/home/mauro/openclaw-mauro"
fi
cd "$ROOT"
PY="${ROOT}/.venv-finanzas/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

mkdir -p data/inbox/boletas/processed data/config/media/inbound logs

if command -v python3 >/dev/null 2>&1; then
  python3 -m pip install --user -q openai python-dotenv 2>/dev/null || true
fi

PY="${ROOT}/.venv-finanzas/bin/python"
if [[ ! -x "$PY" ]]; then PY="python3"; fi

echo "== Lider Gmail =="
"$PY" scripts/lider_receipts_agent.py || true
"$PY" scripts/finanzas_lider_normalize.py || true

echo "== Transferencias Santander =="
"$PY" scripts/transferencias_agent.py || true

echo "== Cartolas Santander (PDF Gmail) =="
"$PY" scripts/santander_cartola_agent.py || true

echo "== Boletas Telegram inbound =="
"$PY" scripts/receipt_vision_agent.py \
  --inbox data/config/media/inbound \
  --processed-dir data/inbox/boletas/processed \
  --merge \
  --source telegram_foto || true

echo "== Boletas inbox manual =="
"$PY" scripts/receipt_vision_agent.py \
  --inbox data/inbox/boletas \
  --merge \
  --source manual || true

echo "== Merge CSV unificado =="
"$PY" scripts/finanzas_merge.py

echo "Listo: $ROOT/data/finanzas_movimientos.csv"
