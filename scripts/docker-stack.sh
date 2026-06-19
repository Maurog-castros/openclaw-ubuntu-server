#!/usr/bin/env bash
# Pausa y reanuda todos los contenedores Docker en ejecución.
# Guarda qué contenedores estaban activos para no levantar los que ya estaban apagados.
set -euo pipefail

STATE_DIR="${DOCKER_STACK_STATE_DIR:-$HOME/.docker-stack-pause}"
STOP_TIMEOUT="${DOCKER_STACK_STOP_TIMEOUT:-10}"
CONTAINERS_FILE="$STATE_DIR/containers.txt"
TIMESTAMP_FILE="$STATE_DIR/timestamp.txt"
META_FILE="$STATE_DIR/meta.tsv"

usage() {
  cat <<'EOF'
Uso: docker-stack.sh <comando>

Comandos:
  pause    Detiene todos los contenedores en ejecución y guarda el estado
  resume   Vuelve a iniciar los contenedores que estaban activos al pausar
  status   Muestra el estado guardado y los contenedores actuales
  help     Muestra esta ayuda

Variables de entorno:
  DOCKER_STACK_STATE_DIR      Directorio del estado (default: ~/.docker-stack-pause)
  DOCKER_STACK_STOP_TIMEOUT   Segundos de gracia al detener (default: 10)

Atajos (si están en PATH):
  docker-stack-pause   -> docker-stack.sh pause
  docker-stack-resume  -> docker-stack.sh resume
EOF
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Error: docker no está instalado o no está en PATH." >&2
    exit 1
  fi
}

priority_for() {
  local name="$1"
  case "$name" in
    postgres-*|redis-*|*postgres*|*redis*) echo 10 ;;
    *ollama*) echo 20 ;;
    *litellm*) echo 30 ;;
    *proxy*|*certbot*|*nginx*) echo 40 ;;
    *) echo 50 ;;
  esac
}

save_state() {
  mkdir -p "$STATE_DIR"

  mapfile -t running < <(docker ps --format '{{.Names}}' | sort)
  if ((${#running[@]} == 0)); then
    echo "No hay contenedores en ejecución."
    exit 0
  fi

  : >"$CONTAINERS_FILE"
  : >"$META_FILE"

  for name in "${running[@]}"; do
    printf '%s\n' "$name" >>"$CONTAINERS_FILE"
    docker inspect "$name" --format \
      '{{.Name}}\t{{index .Config.Labels "com.docker.compose.service"}}\t{{index .Config.Labels "com.docker.compose.project.working_dir"}}\t{{index .Config.Labels "com.docker.compose.project.config_files"}}' \
      | sed 's/^\///' >>"$META_FILE"
  done

  date -Iseconds >"$TIMESTAMP_FILE"
  printf '%s\n' "${#running[@]}"
}

cmd_pause() {
  require_docker
  local count
  count="$(save_state)"
  echo "Pausando $count contenedor(es)..."

  mapfile -t ids < <(docker ps -q)
  if ((${#ids[@]} > 0)); then
    docker stop -t "$STOP_TIMEOUT" "${ids[@]}"
  fi

  echo "Listo. Estado guardado en $STATE_DIR"
  echo "Para volver a encender: docker-stack.sh resume"
}

compose_start_service() {
  local dir="$1"
  local configs="$2"
  local service="$3"

  if [[ -z "$dir" || -z "$service" || ! -d "$dir" ]]; then
    return 1
  fi

  local -a compose_args=()
  if [[ -n "$configs" ]]; then
    local IFS=','
    read -ra files <<<"$configs"
    for file in "${files[@]}"; do
      [[ -f "$file" ]] || continue
      compose_args+=(-f "$file")
    done
  fi

  if ((${#compose_args[@]} == 0)) && [[ -f "$dir/docker-compose.yml" ]]; then
    compose_args=(-f "$dir/docker-compose.yml")
  fi

  if ((${#compose_args[@]} == 0)); then
    return 1
  fi

  (cd "$dir" && docker compose "${compose_args[@]}" start "$service")
}

cmd_resume() {
  require_docker

  if [[ ! -f "$CONTAINERS_FILE" ]]; then
    echo "No hay estado guardado. Ejecuta primero: docker-stack.sh pause" >&2
    exit 1
  fi

  mapfile -t names < <(grep -v '^[[:space:]]*$' "$CONTAINERS_FILE" || true)
  if ((${#names[@]} == 0)); then
    echo "El archivo de estado está vacío." >&2
    exit 1
  fi

  if [[ -f "$TIMESTAMP_FILE" ]]; then
    echo "Reanudando contenedores pausados el $(<"$TIMESTAMP_FILE")..."
  else
    echo "Reanudando contenedores pausados..."
  fi

  declare -A started=()
  declare -A compose_done=()

  # Ordenar por prioridad (bases de datos e infra primero).
  mapfile -t ordered < <(
    for name in "${names[@]}"; do
      printf '%s\t%s\n' "$(priority_for "$name")" "$name"
    done | sort -n -k1,1 -k2,2 | cut -f2
  )

  for name in "${ordered[@]}"; do
    [[ -n "$name" ]] || continue
    if [[ -n "${started[$name]:-}" ]]; then
      continue
    fi

    local service dir configs
    service="$(docker inspect "$name" --format '{{index .Config.Labels "com.docker.compose.service"}}' 2>/dev/null || true)"
    dir="$(docker inspect "$name" --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)"
    configs="$(docker inspect "$name" --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' 2>/dev/null || true)"

    if [[ -n "$service" && -n "$dir" ]]; then
      local key="${dir}|${service}"
      if [[ -z "${compose_done[$key]:-}" ]]; then
        echo "  compose start $service ($dir)"
        if compose_start_service "$dir" "$configs" "$service"; then
          compose_done[$key]=1
          started[$name]=1
          continue
        fi
      elif docker inspect "$name" --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
        started[$name]=1
        continue
      fi
    fi

    echo "  docker start $name"
    if docker start "$name" >/dev/null; then
      started[$name]=1
    else
      echo "  aviso: no se pudo iniciar $name" >&2
    fi
  done

  echo "Listo. Contenedores en ejecución:"
  docker ps --format '  - {{.Names}} ({{.Status}})'
}

cmd_status() {
  require_docker

  echo "Contenedores actuales:"
  if [[ -n "$(docker ps -q)" ]]; then
    docker ps --format '  [up]   {{.Names}} ({{.Status}})'
  else
    echo "  (ninguno en ejecución)"
  fi

  echo
  if [[ ! -f "$CONTAINERS_FILE" ]]; then
    echo "No hay estado de pausa guardado."
    return 0
  fi

  echo "Estado guardado en $STATE_DIR:"
  if [[ -f "$TIMESTAMP_FILE" ]]; then
    echo "  Pausado el: $(<"$TIMESTAMP_FILE")"
  fi

  mapfile -t saved < <(grep -v '^[[:space:]]*$' "$CONTAINERS_FILE" || true)
  echo "  Contenedores pausados (${#saved[@]}):"
  for name in "${saved[@]}"; do
    if docker ps --format '{{.Names}}' | grep -qx "$name"; then
      echo "  [up]   $name"
    elif docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
      echo "  [down] $name"
    else
      echo "  [?]    $name (ya no existe)"
    fi
  done
}

main() {
  local cmd="${1:-}"
  local invoked
  invoked="$(basename "${0##*/}")"

  case "$invoked" in
    docker-stack-pause|dstack-pause) cmd="pause" ;;
    docker-stack-resume|dstack-resume) cmd="resume" ;;
  esac

  cmd="${cmd:-help}"
  case "$cmd" in
    pause|stop|down) cmd_pause ;;
    resume|start|up) cmd_resume ;;
    status) cmd_status ;;
    help|-h|--help) usage ;;
    *)
      echo "Comando desconocido: $cmd" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
