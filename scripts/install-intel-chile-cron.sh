#!/usr/bin/env bash
# Cron Intel Daily Chile → WhatsApp 09:00 y 19:00 (America/Santiago en el host).
set -euo pipefail

REPO="${OPENCLAW_REPO:-/home/mauro/openclaw-mauro}"
MORNING="${INTEL_CHILE_CRON_MORNING:-0 9 * * *}"
EVENING="${INTEL_CHILE_CRON_EVENING:-0 19 * * *}"

CRON_MORNING="$MORNING cd $REPO && bash scripts/run-intel-chile-daily-whatsapp.sh morning # openclaw-intel-chile-morning"
CRON_EVENING="$EVENING cd $REPO && bash scripts/run-intel-chile-daily-whatsapp.sh evening # openclaw-intel-chile-evening"

current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "$current" \
  | grep -v 'run-intel-chile-daily-whatsapp.sh' \
  | grep -v 'openclaw-intel-chile-morning' \
  | grep -v 'openclaw-intel-chile-evening' \
  || true)"

printf '%s\n%s\n%s\n' "$filtered" "$CRON_MORNING" "$CRON_EVENING" | sed '/^$/d' | crontab -

echo "Cron Intel Daily Chile instalado:"
crontab -l | grep -E 'intel-chile|openclaw-intel-chile' || true
