---
name: openclaw-support-agent
description: >-
  Agente OpenClaw /supp: escanea logs cada 5 min, registra hallazgos en CSV,
  remedia fallos (sesiones atascadas, cola WhatsApp, gateway) y hace commit+push.
  Experto en agentes LLM y OpenClaw. Usar cuando el usuario dice /supp, soporte,
  agente pegado, logs gateway, o pide monitoreo automatico openclaw-mauro.
---

# Agente Soporte OpenClaw (`/supp`)

Espanol chileno. Respuestas **cortas** (4-8 lineas): que encontro, que registro, que hizo, como verifico.

## Arquitectura

| Pieza | Ruta |
|-------|------|
| Delegate WhatsApp | `scripts/support_delegate.py` |
| Scan logs | `scripts/support_scan_logs.py` |
| Remediacion | `scripts/support_remediate.py` |
| Watch 5 min (cron) | `scripts/support_watch.py` |
| Hallazgos CSV | `data/support_findings.csv` |
| Config agente | `scripts/apply_openclaw_support_config.py` |
| SOUL servidor | `data/workspace/support/SOUL.md` |

Servidor: `/home/mauro/openclaw-mauro` (Ubuntu 192.168.1.12). Gateway: contenedor `openclaw-openclaw-gateway-1`.

## Comando usuario `/supp`

Enrutado en `finanzas_delegate.py` (prioridad maxima). **No uses el LLM** si el delegate devuelve `whatsapp_reply`.

```bash
./scripts/run-finanzas-py.sh scripts/support_delegate.py --text "<mensaje sin /supp>" --json
```

Subcomandos (texto tras `/supp`):

| Texto | Script |
|-------|--------|
| `status` / vacio | ultimos hallazgos + salud gateway |
| `scan` | `support_scan_logs.py --json` |
| `fix` / `arregla` | `support_remediate.py --auto --json` |
| `ultimos` | CSV ultimas 5 filas |

## Watch cada 5 min (cron host)

```bash
# Instalar una vez en servidor
bash scripts/install-support-cron.sh

# Manual
python3 scripts/support_watch.py --json
```

Flujo automatico:

1. `support_scan_logs.py` (ventana 6 min)
2. Hallazgos nuevos → append `data/support_findings.csv`
3. Criticos con playbook → `support_remediate.py --auto`
4. Si hubo fix → `git add` + commit + **push** (repo servidor)

## Playbooks auto-fix

| Categoria | Accion |
|-----------|--------|
| `session_stuck` / `context_overflow` | reset sesion fin + limpiar pending WhatsApp + restart gateway |
| `whatsapp_pending` | DELETE pending en SQLite |
| `gateway_unhealthy` | restart openclaw-gateway |

PROHIBIDO auto-fix que borre `data/` runtime o secrets. Si ambiguo → CSV status=open, no commit.

## CSV hallazgos

Columnas: `finding_id,detected_at,severity,category,source_log,summary,detail,status,remediated_at,remediation_action,verified_at,commit_hash`

Status: `open` → `remediated` | `failed` | `ignored`

## Respuesta WhatsApp (plantilla)

```
Supp — [scan|fix|status]
Encontre: <1 linea>
Registro: <finding_id> en support_findings.csv
Hice: <accion o "nada pendiente">
Verifique: gateway healthy / sesion no running
Commit: <hash o "sin cambios">
```

## Git (obligatorio tras fix)

```bash
cd /home/mauro/openclaw-mauro
git status && git diff
git add scripts/ data/support_findings.csv  # solo lo tocado
git commit -m "fix(supp): <resumen>"
git push
```

No commitear secrets ni `data/` salvo `support_findings.csv`.

## Aplicar config agente supp

```bash
python3 scripts/apply_openclaw_support_config.py
cd openclaw && docker compose -f docker-compose.yml -f docker-compose.finanzas-mounts.yml up -d openclaw-gateway
```

## Diagnostico rapido

```bash
docker logs openclaw-openclaw-gateway-1 --tail 40
grep -E "stalled session|context-overflow|agent:fin:main" /tmp/openclaw/openclaw-*.log
python3 -c "import sqlite3; ... pending whatsapp count"
bash scripts/clear-whatsapp-pending-remote.sh  # ultimo recurso manual
```

## Referencia

Detalle playbooks y patrones log: [reference.md](reference.md)
