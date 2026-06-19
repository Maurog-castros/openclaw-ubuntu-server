#!/usr/bin/env bash
# Instala cron diario Jobs recommended CSV (08:30).
set -euo pipefail

REPO="${OPENCLAW_REPO:-/home/mauro/Dev/openclaw-mauro}"
SCHEDULE="${JOBS_RECOMMENDED_CRON_SCHEDULE:-30 8 * * *}"
CRON_CMD="$SCHEDULE cd $REPO && bash scripts/run-jobs-recommended-daily.sh # openclaw-jobs-recommended-daily"

current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "$current" | grep -v 'run-jobs-recommended-daily.sh' | grep -v 'openclaw-jobs-recommended-daily' || true)"
printf '%s\n%s\n' "$filtered" "$CRON_CMD" | sed '/^$/d' | crontab -

echo "Cron Jobs recommended instalado:"
echo "  $CRON_CMD"
crontab -l | grep -E 'jobs-recommended|openclaw-jobs-recommended' || true
