#!/usr/bin/env bash
# Quita el cron diario de Jobs (postulaciones LinkedIn + WhatsApp).
set -euo pipefail

current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "$current" \
  | grep -v 'run-jobs-daily-auto-whatsapp.sh' \
  | grep -v 'openclaw-jobs-daily' \
  | grep -v 'jobs_daily_auto' \
  || true)"

printf '%s\n' "$filtered" | sed '/^$/d' | crontab -

echo "Cron Jobs desinstalado."
if crontab -l 2>/dev/null | grep -qE 'jobs-daily|openclaw-jobs'; then
  echo "AVISO: aun quedan lineas jobs en crontab; revisa con: crontab -l"
  exit 1
fi
echo "OK: sin entradas jobs en crontab."
