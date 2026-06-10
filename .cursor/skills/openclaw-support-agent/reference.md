# Referencia — patrones log y remediacion

## Fuentes

- `docker logs openclaw-openclaw-gateway-1`
- `/tmp/openclaw/openclaw-YYYY-MM-DD.log` (dentro del contenedor)
- `data/config/state/openclaw.sqlite` (plugin_state_entries whatsapp pending)
- `data/config/agents/finanzas/sessions/sessions.json` (status running)

## Patrones

| Regex / condicion | category | severity |
|-------------------|----------|----------|
| `stalled session.*agent:fin:main` | session_stuck | critical |
| `context-overflow-precheck` + sin `Sent message` despues 3 min | context_overflow | critical |
| `namespace LIKE inbound.v1.pending%` count > 0 | whatsapp_pending | warning |
| gateway status != healthy | gateway_unhealthy | critical |
| `Ollama could not be reached` | ollama_unreachable | info |
| `agent:fin:main` status=running age > 600s | session_stuck | critical |

## Remediacion session_stuck

Equivalente a `clear-whatsapp-pending-remote.sh` pero sin duplicar si ya healthy:

1. Backup SQLite
2. DELETE pending whatsapp
3. reset_finanzas_whatsapp_session.sh (agent:fin:main)
4. docker compose restart openclaw-gateway
5. Verificar: `docker compose ps` healthy + no running session > 60s

## Verificacion post-fix

```bash
./scripts/run-finanzas-py.sh scripts/support_scan_logs.py --json
# expect: new findings status remediated, gateway ok
```
