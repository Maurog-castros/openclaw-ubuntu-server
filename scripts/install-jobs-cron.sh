#!/usr/bin/env bash
# Instala cron diario Jobs: buscar + postular 3 vacantes + WhatsApp (09:00).
# Pausado por defecto: usar uninstall-jobs-cron.sh. Reactivar solo si jobs funciona bien.
set -euo pipefail

REPO="${OPENCLAW_REPO:-/home/mauro/openclaw-mauro}"
# Ajusta hora aqui si quieres (min hora dia mes dow)
SCHEDULE="${JOBS_CRON_SCHEDULE:-0 9 * * *}"
CRON_CMD="$SCHEDULE cd $REPO && bash scripts/run-jobs-daily-auto-whatsapp.sh # openclaw-jobs-daily"

current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "$current" | grep -v 'run-jobs-daily-auto-whatsapp.sh' | grep -v 'openclaw-jobs-daily' || true)"
printf '%s\n%s\n' "$filtered" "$CRON_CMD" | sed '/^$/d' | crontab -

echo "Cron Jobs instalado:"
echo "  $CRON_CMD"
crontab -l | grep -E 'jobs-daily|openclaw-jobs' || true
