# Agente `supp` 🛠

**Prefijo:** `/supp`  
**Descripción:** Soporte técnico OpenClaw — logs, remediación, hallazgos CSV.

## Qué hace

- Diagnóstico de agentes LLM y gateway OpenClaw
- Lectura de logs, sesiones, configuración
- Remediación con scripts `support_*.py`
- Escaneo de errores y export de hallazgos

## Delegate

```sh
/home/node/openclaw-mauro/scripts/run-finanzas-py.sh \
  /home/node/openclaw-mauro/scripts/support_delegate.py --text "<mensaje>" --json
```

## Tools

`read`, `exec` (full, ask off), `message`, `memory_search`, `memory_get` — sin `write`/`edit`.

## Workspace

`/home/node/.openclaw/workspace/support`  
Referencia: `support/AGENTS.md`, scripts `support_*.py`
