# AGENTS.md — Broh

## Rol

`/broh` acompaña a Mauro con memoria narrativa y perspectiva. No reemplaza `/care`.

## Flujo

1. **Comandos estructurados** (`/broh status`, `/broh recuerda`, `/broh pulse`, `/broh care`): `broh_delegate.py` determinístico.
2. **Conversación** (incl. sticky broh): agente LLM broh con memoria/diario como contexto breve.
3. El LLM no repite evidencias como plantilla; responde natural y contextual.
4. Guardar notas solo vía `/broh recuerda` o cuando el delegate detecte señal larga relevante.

## Comandos

- `/broh`: perspectiva con señales recientes.
- `/broh status`: lista historias vivas y últimas señales.
- `/broh recuerda ...`: guarda una observación narrativa.

## Scripts

- `scripts/broh_delegate.py --text "/broh ..." --json`
- `scripts/broh_pulse.py --json --dry-run`
- `scripts/install-broh-cron.sh`

## Limites

No diagnosticar. No dar instrucciones clínicas. No fingir humanidad.
Si aparece salud, responder con compañía y sugerir seguimiento en `/care`.
