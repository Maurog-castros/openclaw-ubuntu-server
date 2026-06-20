# Agente `broh`

**Prefijo:** `/broh`  
**Modelo OpenClaw:** `openclaw/broh`  
**Descripción:** Compañía narrativa — perspectiva empática basada en memoria de historias de Mauro.

## Qué hace

- **Conversación** — tono cercano, chileno neutro; máx. ~500 chars en WhatsApp
- **Memoria narrativa** — `data/stories.json`, `data/observations.jsonl`
- **Pulso proactivo** — cron `broh_pulse.py` con estado en `data/pulse_state.json`
- **Continuidad** — historias: tinnitus, transición laboral, OpenClaw, aprendizaje

## Delegate

WhatsApp/Telegram: `/broh` → `broh_delegate.py` (sesión LLM + contexto Broh).

## Scripts

`broh_delegate.py`, `broh_pulse.py`, `apply_openclaw_broh_config.py`

## Workspace

`/home/node/.openclaw/workspace/broh`  
Detalle: `broh/SOUL.md`, `broh/AGENTS.md`, `broh/TOOLS.md`

## No es

No es terapeuta ni médico. Seguimiento clínico → derivar a `/care`.
