#!/usr/bin/env bash
set -euo pipefail

ROOT="${OPENCLAW_ROOT:-/home/mauro/Dev/openclaw-mauro}"
OPENCLAW_DIR="$ROOT/openclaw"
ACTIVE="$OPENCLAW_DIR/litellm-config.yaml"
LMSTUDIO="$OPENCLAW_DIR/litellm-config.lmstudio.yaml"
IAMIKO_BACKUP="$OPENCLAW_DIR/litellm-config.iamiko.yaml"

usage() {
  cat <<'EOF'
Uso: use-lmstudio-backend.sh <lmstudio|iamiko|status>

  lmstudio  Enruta openclaw-remote* a LM Studio (host.docker.internal:1234)
  iamiko    Restaura backend Iamiko (ia.iamiko.cl)
  status    Muestra qué perfil está activo

Variables:
  OPENCLAW_ROOT  Raíz del proyecto (default: /home/mauro/Dev/openclaw-mauro)
EOF
}

ensure_iamiko_backup() {
  if [[ ! -f "$IAMIKO_BACKUP" ]]; then
    if grep -q 'ia.iamiko.cl' "$ACTIVE" 2>/dev/null; then
      cp "$ACTIVE" "$IAMIKO_BACKUP"
      echo "Backup Iamiko guardado en $IAMIKO_BACKUP"
    elif [[ -f "$ACTIVE" ]]; then
      echo "Aviso: $ACTIVE no apunta a Iamiko; backup no creado." >&2
    fi
  fi
}

compose_restart() {
  if ! docker ps --format '{{.Names}}' | grep -qE 'litellm|openclaw-gateway'; then
    echo "Contenedores aún no en ejecución; omitiendo restart (usa docker-stack-resume)."
    return 0
  fi
  (
    cd "$OPENCLAW_DIR"
    docker compose restart litellm openclaw-gateway
  )
}

cmd_lmstudio() {
  [[ -f "$LMSTUDIO" ]] || { echo "Falta $LMSTUDIO" >&2; exit 1; }
  ensure_iamiko_backup
  cp "$LMSTUDIO" "$ACTIVE"
  echo "Activo: LM Studio (host.docker.internal:1234)"
  compose_restart
  echo "LiteLLM health:"
  curl -sf "http://127.0.0.1:4000/health/liveliness" && echo || echo "  (litellm aún no responde)"
}

cmd_iamiko() {
  if [[ -f "$IAMIKO_BACKUP" ]]; then
    cp "$IAMIKO_BACKUP" "$ACTIVE"
  else
    echo "No hay backup Iamiko en $IAMIKO_BACKUP" >&2
    exit 1
  fi
  echo "Activo: Iamiko (ia.iamiko.cl)"
  compose_restart
  echo "LiteLLM health:"
  curl -sf "http://127.0.0.1:4000/health/liveliness" && echo || echo "  (litellm aún no responde)"
}

cmd_status() {
  if grep -q 'host.docker.internal:1234' "$ACTIVE" 2>/dev/null; then
    echo "Perfil activo: lmstudio"
  elif grep -q 'ia.iamiko.cl' "$ACTIVE" 2>/dev/null; then
    echo "Perfil activo: iamiko"
  else
    echo "Perfil activo: desconocido"
  fi
  echo "Archivo: $ACTIVE"
}

main() {
  local cmd="${1:-status}"
  case "$cmd" in
    lmstudio) cmd_lmstudio ;;
    iamiko) cmd_iamiko ;;
    status) cmd_status ;;
    -h|--help|help) usage ;;
    *)
      echo "Comando desconocido: $cmd" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
