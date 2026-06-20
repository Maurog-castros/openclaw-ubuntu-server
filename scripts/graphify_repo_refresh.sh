#!/usr/bin/env bash
# Refresh graphify graph and compact index for support lookups.
set -euo pipefail

ROOT="/home/mauro/Dev/openclaw-mauro"
cd "$ROOT"
mkdir -p graphify-out runtime/logs

if command -v graphify >/dev/null 2>&1; then
  graphify . --update --no-viz >> runtime/logs/graphify-refresh.log 2>&1 || true
else
  echo "$(date -Is) graphify CLI not installed; indexing existing graph only" >> runtime/logs/graphify-refresh.log
fi

python3 scripts/graphify_repo_index.py --json >> runtime/logs/graphify-refresh.log 2>&1
