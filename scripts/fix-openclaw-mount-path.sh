#!/usr/bin/env bash
# Restaura /home/mauro/openclaw-mauro como symlink al repo real en Dev.
# Docker y scripts del repo esperan esa ruta canónica.
set -euo pipefail

CANONICAL="/home/mauro/openclaw-mauro"
REPO="/home/mauro/Dev/openclaw-mauro"

if [[ ! -d "$REPO" ]]; then
  echo "ERROR: no existe el repo en $REPO" >&2
  exit 1
fi

if [[ -L "$CANONICAL" ]]; then
  current="$(readlink -f "$CANONICAL")"
  if [[ "$current" == "$(readlink -f "$REPO")" ]]; then
    echo "OK: $CANONICAL ya apunta a $REPO"
    exit 0
  fi
  echo "Reemplazando symlink existente ($current -> $REPO)"
  sudo rm "$CANONICAL"
elif [[ -e "$CANONICAL" ]]; then
  echo "Eliminando directorio roto en $CANONICAL (requiere sudo)..."
  sudo rm -rf "$CANONICAL"
fi

sudo ln -s "$REPO" "$CANONICAL"
echo "Symlink creado: $CANONICAL -> $REPO"
ls -la "$CANONICAL"
