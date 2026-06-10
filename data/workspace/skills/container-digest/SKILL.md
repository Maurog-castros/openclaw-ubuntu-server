---
name: container-digest
description: "Resumen ejecutivo de logs recientes de TODOS los contenedores Docker del host. OBLIGATORIO: ejecutar docker logs por cada contenedor y sintetizar con timestamps, errores, warnings. Trigger: 'resumen contenedores', 'logs containers', 'que paso en docker', 'estado servicios', 'que ha ocurrido'."
---

# container-digest — Resumen ejecutivo de containers

**REGLA CRITICA: este skill NO se considera completado hasta que se hayan leido logs de CADA contenedor activo y se haya producido el resumen formateado abajo. Listar containers SIN leer logs = INCOMPLETO. Repite hasta cubrir todos.**

## Procedimiento OBLIGATORIO

Ejecutar TODOS los pasos en orden. No saltarse ninguno.

### Paso 1: Enumerar contenedores

```sh
docker ps --format '{{.Names}}'
```

Guardar lista. Si lista vacia: reportar "sin contenedores activos" y terminar.

### Paso 2: Para CADA contenedor de la lista, leer logs

Para cada `<name>` ejecutar:

```sh
docker logs --tail 100 --since=24h --timestamps <name> 2>&1 | tail -100
```

(Ajustar `--since` solo si usuario pidio ventana distinta. Default 24h.)

NO procesar contenedores en batch ignorando alguno. CADA UNO.

### Paso 3: Por contenedor, extraer

- **Status actual** (de `docker ps`): Up Xh, healthy/unhealthy
- **Ultimo timestamp** visto en logs (formato `YYYY-MM-DD HH:MM:SS`)
- **Ultima accion** notable (1 linea, lo mas reciente significativo)
- **Errores** detectados: contar, mostrar 1 ejemplo truncado a 120 chars
- **Warnings**: contar, ejemplo si relevante
- **Eventos especiales**: restarts, crashes, OOM, rate-limits, auth fails

### Paso 4: Sintesis final

**OBLIGATORIO usar este formato exacto Markdown:**

```
## <container-name>
- **Status:** <Up Xh (healthy|unhealthy|starting)>
- **Ultimo evento:** `<YYYY-MM-DD HH:MM:SS>` <descripcion breve>
- **Errores:** <N> <(ejemplo: "...")>
- **Warnings:** <N> <(ejemplo: "...")>
- **Notas:** <restarts/crashes/anomalias si las hay, o "ninguna">
```

Una seccion por contenedor. Al final, linea resumen global:

```
**Total:** N containers | Errores: X | Warnings: Y | Unhealthy: Z
```

## Patrones a destacar siempre

Si aparecen en logs, mencionar explicito en "Errores" o "Notas":
- `error|ERROR|FATAL|CRITICAL|panic|exception|traceback`
- `429|rate limit|quota|RateLimitError`
- `connection refused|timeout|EHOSTUNREACH|ECONNREFUSED|ETIMEDOUT`
- `OOMKilled|out of memory|killed`
- `unhealthy|restart|exited`
- `auth fail|401|403|forbidden|unauthorized`

## Filtros de seguridad

ANTES de mostrar lineas de log, omitir/redactar:
- Lineas con `token=`, `api_key=`, `password=`, `bearer `, `Authorization:`
- JWT-like strings (3 partes separadas por `.` largas)
- Secrets en formato `xx-XXXXXXXXX`

Si redactaste algo, marca `[REDACTED]` en el ejemplo.

## Manejo de errores del propio skill

- Si `docker logs <name>` falla: reportar el container con "logs no disponibles: <error>"
- Si `docker ps` falla: detener y reportar el error al usuario
- Si un contenedor tiene >500 lineas de error spam: agregar "log volume alto (Nk lineas)"

## Si usuario pide contenedor especifico

Solo procesar ese. Skipear paso 1 enumeracion. Saltar a paso 2 con ese nombre.

## Si usuario pide ventana de tiempo

- "ultima hora" -> `--since=1h`
- "ultimas 6 horas" -> `--since=6h`
- "hoy" -> `--since=$(date +%Y-%m-%dT00:00:00)`
- "ultimos 10 minutos" -> `--since=10m`

## Recordatorio final

NO terminar respondiendo solo con `docker ps`. El usuario explicito quiere el RESUMEN EJECUTIVO con timestamps y errores. Ejecutar paso 2 sin falta.
