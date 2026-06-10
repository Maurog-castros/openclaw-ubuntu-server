---
name: host-status
description: "Reporte completo del servidor Ubuntu host: uptime, CPU/RAM/disco, servicios systemd, puertos abiertos, contenedores Docker, modelos Ollama, errores kernel/auth recientes. Trigger: 'estado servidor', 'como esta el ubuntu', 'estado del host', 'salud del servidor', 'que esta pasando en el server', 'reporte servidor'."
---

# host-status — Reporte ejecutivo del host Ubuntu

OpenClaw corre dentro de Docker. Para leer estado real del host SIEMPRE usar `host-sh "<cmd>"` (SSH al host real). Para contenedores leer logs con `docker logs` (que internamente via host-wrap llega al host).

**REGLA CRITICA: no responder hasta haber ejecutado TODOS los pasos de la lista. El usuario quiere reporte COMPLETO. Resumen parcial = INCOMPLETO.**

## Procedimiento OBLIGATORIO

Ejecutar en orden. No saltarse pasos.

### 1. Identidad y uptime

```sh
host-sh "hostname && uptime && uname -r"
```

### 2. Recursos: CPU, RAM, swap, disco, load

```sh
host-sh "free -h && echo --- && df -h --output=source,size,used,avail,pcent,target | grep -vE 'tmpfs|udev|loop' && echo --- && uptime"
```

Extraer:
- RAM usada/total y %, swap usado
- Disco / usado %, otras mounts >80%
- Load avg 1/5/15 min

Si load > nproc o RAM > 90% o disco > 85%, marcar **WARN**.

### 3. Top procesos

```sh
host-sh "ps -eo pcpu,pmem,pid,comm --sort=-pcpu | head -8"
```

Reportar top 3 si alguno > 20% CPU o > 10% RAM.

### 4. Servicios systemd criticos

```sh
host-sh "systemctl is-active docker containerd ssh chrony cron ufw 2>/dev/null"
```

Listar cuales no estan `active`.

```sh
host-sh "systemctl list-units --type=service --state=failed --no-pager --no-legend"
```

Si hay servicios failed: listarlos.

### 5. Red: puertos publicos

```sh
host-sh "ss -tlnp 2>/dev/null | awk 'NR>1 {print \$4, \$6}' | sort -u"
```

Identificar puertos en `0.0.0.0:*` (expuestos LAN).

### 6. Docker stack

```sh
docker ps --format '{{.Names}}|{{.Status}}|{{.Ports}}'
```

Contar: total, healthy, unhealthy, restarting.

### 7. Ollama: modelos y carga actual

```sh
docker exec openclaw-ollama-fast-1 ollama list 2>&1
docker exec openclaw-ollama-fast-1 ollama ps 2>&1
```

Reportar:
- Modelos disponibles (nombre + tamaño)
- Modelo activo en memoria (si hay)
- Tiempo restante de eviction (si aplica)

### 8. Logs recientes con errores

```sh
host-sh "journalctl -p err -n 20 --no-pager --since '1 hour ago'"
host-sh "tail -30 /var/log/auth.log 2>/dev/null | grep -iE 'fail|invalid|refused' | tail -10"
```

Resumir cuenta de errores por origen.

### 9. Litellm health (puente a modelos)

```sh
docker exec openclaw-litellm-1 sh -c "curl -s http://localhost:4000/health/liveliness"
```

Esperar `{"status":"healthy"}`. Si no, marcar **FAIL**.

### 10. Container digest breve

Para cada container Docker activo, ultimas 30 lineas y contar errores:

```sh
docker logs --tail 30 --since=1h <name> 2>&1 | grep -ciE "error|fatal|panic|exception|429" || echo 0
```

Reportar `<name>: N errores ultima hora`.

## Formato de salida (OBLIGATORIO)

```
# Estado del servidor Ubuntu — `<hostname>`

**Resumen:** OK | WARN | FAIL — <una linea>

## Sistema
- Uptime: <X dias Yh>
- Kernel: <version>
- Load: <1m / 5m / 15m>
- RAM: <usada>/<total> (<%>)
- Swap: <usado>/<total>
- Disco /: <usado>/<total> (<%>)
- Otros mounts saturados: <none | lista>

## Procesos top
- <comando> <cpu%> <ram%>
(solo si > umbral)

## Servicios systemd
- Criticos: <X/Y activos>
- Failed: <none | lista>

## Red
- Puertos publicos: <lista de puerto:proceso>
- Total listening: N

## Docker (N containers)
- Healthy: X
- Unhealthy/Restarting: <none | lista>
- Errores ultima hora por container:
  - <name>: <N>

## Ollama
- Modelos: <lista nombre + size>
- Activo en RAM: <none | <name> hasta <T>>

## LiteLLM
- Health: OK | FAIL

## Errores recientes (1h)
- journalctl err: <N>
- auth fail: <N>
- Ejemplo destacado: <linea truncada 120c>

## Acciones recomendadas
<solo si hay WARN/FAIL: 1-3 bullets accionables>
```

## Reglas

- NO mostrar tokens/keys/passwords. Redactar con `[REDACTED]`.
- Si un paso falla: continuar y reportar el fallo en su seccion.
- Si usuario pide subset (solo ollama, solo disco, etc): saltarse al paso correspondiente.
- Default ventana errores: 1h. Ajustar si usuario pide.
- Responder en espanol.
- No inventar metricas: si comando fallo, decir "no disponible".

## Edge cases

- `host-sh` falla: probar `docker exec openclaw-openclaw-gateway-1 host-sh "..."` o reportar perdida acceso host.
- nvidia-smi no existe: omitir GPU section (este host es CPU only).
- ollama vacio: reportar "sin modelos cargados".
