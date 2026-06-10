#!/usr/bin/env bash
# Cron cada 5 min: support_watch.py en servidor Ubuntu.
set -euo pipefail
REPO="${OPENCLAW_REPO:-/home/mauro/openclaw-mauro}"
CRON_CMD="*/5 * * * * cd $REPO && /usr/bin/python3 scripts/support_watch.py >> data/support_watch.log 2>&1"
current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "$current" | grep -v 'support_watch.py' || true)"
printf '%s\n%s\n' "$filtered" "$CRON_CMD" | sed '/^$/d' | crontab -
echo "Cron instalado: $CRON_CMD"
crontab -l | grep support_watch || true
