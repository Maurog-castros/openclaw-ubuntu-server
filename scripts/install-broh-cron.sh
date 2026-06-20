#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/mauro/Dev/openclaw-mauro"
MARKER="openclaw-broh-pulse"
LINE="17 10-21 * * * $ROOT/scripts/run-broh-pulse-whatsapp.sh >> $ROOT/runtime/logs/broh-pulse.log 2>&1 # $MARKER"

mkdir -p "$ROOT/runtime/logs"
chmod +x "$ROOT/scripts/run-broh-pulse-whatsapp.sh"

(crontab -l 2>/dev/null | grep -v "$MARKER"; echo "$LINE") | crontab -
echo "OK: cron instalado ($MARKER)"
