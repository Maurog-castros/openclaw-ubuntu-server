#!/bin/sh
set -e

BUN_BIN="/home/node/.bun/bin/bun"

if [ ! -x "$BUN_BIN" ]; then
  echo "[ensure-bun] Installing bun into /home/node/.bun ..."
  curl -fsSL https://bun.sh/install | bash
fi
