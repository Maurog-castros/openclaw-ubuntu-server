#!/usr/bin/env bash
# Install weekly graphify refresh cron. Idempotent.
set -euo pipefail

ROOT="/home/mauro/Dev/openclaw-mauro"
MARK="# openclaw-graphify-refresh"
LINE="23 4 * * 0 cd $ROOT && flock -n /tmp/openclaw-graphify-refresh.lock bash scripts/graphify_repo_refresh.sh $MARK"

tmp="$(mktemp)"
crontab -l 2>/dev/null | grep -vF "$MARK" > "$tmp" || true
printf '%s\n' "$LINE" >> "$tmp"
crontab "$tmp"
rm -f "$tmp"
echo "installed $MARK"
