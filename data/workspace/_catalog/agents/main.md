# Agente `main`

**Prefijo:** ninguno (agente por defecto del gateway y dashboard)  
**Descripción:** Orquestador general — **dueño del canal** WhatsApp/Telegram, host Docker, repos.

## Qué hace

- **Canal:** PASO 1 siempre `channel_delegate.py` → copia `whatsapp_reply` (enruta a fin, care, hlgo, …)
- Diagnóstico del host Ubuntu vía `host-sh "..."` (OpenClaw corre en Docker)
- Estado Docker, servicios, repos en `/home/node/repos`
- Gmail Watch y Gmail Organize (scripts finanzas)
- Responde preguntas sobre otros agentes leyendo `_catalog/agents/`
- Solo si `delegate_miss`: usa tools/scripts del especialista

## Workspace

`/home/node/.openclaw/workspace` (raíz compartida)

## Tools

`read`, `write`, `edit`, `exec`, `process`, `web_search`, `memory_search`, `memory_get`
