#!/bin/sh
set -e

for wrapper in /home/node/openclaw-mauro/scripts/run-finanzas-py.sh /home/node/openclaw-mauro/scripts/run-vida-py.sh; do
  if [ -f "$wrapper" ]; then
    chmod +x "$wrapper" 2>/dev/null || true
  fi
done

BUN_BIN="/home/node/.bun/bin/bun"

if [ ! -x "$BUN_BIN" ]; then
  echo "[ensure-bun] Installing bun into /home/node/.bun ..."
  curl -fsSL https://bun.sh/install | bash
fi
