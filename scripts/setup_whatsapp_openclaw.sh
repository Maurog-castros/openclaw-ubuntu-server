#!/usr/bin/env bash
# Vincula WhatsApp (QR) al gateway OpenClaw — mismo flujo que Telegram/finanzas.
set -euo pipefail

ROOT="/home/mauro/openclaw-mauro"
COMPOSE="docker compose -f ${ROOT}/openclaw/docker-compose.yml"
CLI="${COMPOSE} exec -T openclaw-cli"
AUTH_HOST="${ROOT}/data/config/whatsapp-auth/default"
AUTH_CONTAINER="/home/node/.openclaw/whatsapp-auth/default"
ALLOW_FILE="${ROOT}/secrets/whatsapp_allow_from.txt"

mkdir -p "${AUTH_HOST}" "${ROOT}/secrets"

if [[ ! -f "${ALLOW_FILE}" ]]; then
  cat >"${ALLOW_FILE}" <<'EOF'
# Tu numero personal E.164 (quien escribe al bot de finanzas). Uno por linea.
# Ejemplo Chile: +56912345678
+56900000000
EOF
  echo "Edita ${ALLOW_FILE} con tu numero real antes de continuar."
fi

echo "== Aplicar config finanzas + WhatsApp =="
python3 "${ROOT}/scripts/apply_openclaw_finanzas_config.py"

echo "== Registrar canal WhatsApp =="
${CLI} openclaw channels add \
  --channel whatsapp \
  --account default \
  --auth-dir "${AUTH_CONTAINER}" \
  --name "OpenClaw Finanzas" 2>/dev/null || true

echo "== Reiniciar gateway =="
${COMPOSE} restart openclaw-gateway
sleep 8

echo ""
echo "============================================================"
echo " SIGUIENTE PASO: escanear QR con el telefono del numero nuevo"
echo "============================================================"
echo ""
echo "En el telefono dedicado OpenClaw:"
echo "  WhatsApp -> Dispositivos vinculados -> Vincular dispositivo"
echo ""
echo "Corre en SSH INTERACTIVO (no -T), desde tu PC:"
echo ""
echo "  ssh -t mauro@192.168.1.12 \\"
echo "    'cd ${ROOT}/openclaw && docker compose exec openclaw-cli openclaw channels login --channel whatsapp --account default'"
echo ""
echo "Verificar estado:"
echo "  ${CLI} openclaw channels status --deep"
echo ""
echo "Si usas pairing (dmPolicy=pairing), aprueba tu numero:"
echo "  ${CLI} openclaw pairing list whatsapp"
echo "  ${CLI} openclaw pairing approve whatsapp <CODIGO>"
echo ""
