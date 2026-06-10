#!/usr/bin/env bash
# Corrige symlink roto data/config/finanzas_data -> .. (bucle infinito en git/find).
set -eu
ROOT="${OPENCLAW_REPO:-/home/mauro/openclaw-mauro}"
TARGET="$ROOT/data/config/finanzas_data"

if [[ -L "$TARGET" ]]; then
  LINK="$(readlink "$TARGET")"
  echo "Symlink actual: $TARGET -> $LINK"
  if [[ "$LINK" == ".." ]]; then
    rm "$TARGET"
    echo "Eliminado symlink circular."
  fi
fi

if [[ ! -e "$TARGET" ]]; then
  mkdir -p "$TARGET/inbox/boletas"
  echo "Creado directorio real: $TARGET/inbox/boletas"
fi

# Opcional: compartir inbox con data/inbox/boletas del host
INBOX="$ROOT/data/inbox/boletas"
if [[ -d "$INBOX" && ! -e "$TARGET/inbox/boletas" ]]; then
  ln -sfn "$INBOX" "$TARGET/inbox/boletas"
  echo "Enlazado inbox -> $INBOX"
fi

echo "OK. Verifica: ls -la $TARGET"
