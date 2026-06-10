---
name: intel-youtube
description: >-
  Resume videos de YouTube (puntos clave en espanol), debate el contenido con el usuario
  y registra insights en el workspace Intel. Usar cuando el usuario pasa un link de YouTube,
  pide resumir un video, debatir un video, o registrar insights de contenido audiovisual.
---

# Intel YouTube — resumen, debate e insights

Agente: **intel**. Espanol chileno tecnico. Respuestas compactas para WhatsApp.

## Arquitectura

| Pieza | Ruta |
|-------|------|
| Script principal | `scripts/intel_youtube.py` |
| Delegate | `scripts/intel_delegate.py` |
| Resumenes | `data/workspace/marketing/intel/youtube/summaries/` |
| Sesiones debate | `data/workspace/marketing/intel/youtube/sessions/` |
| Insights JSONL | `data/workspace/marketing/intel/youtube/insights.jsonl` |
| Insights MD | `data/workspace/marketing/intel/insights/youtube.md` |
| Sesion activa | `data/intel_youtube_session.json` (TTL 2h) |

## Flujo

### 1. Link YouTube → resumen

```bash
./scripts/run-finanzas-py.sh scripts/intel_youtube.py --url "<url>" --summarize --json
```

Devuelve `whatsapp_reply` con puntos clave, insights Mauro y accionables. **Copiar tal cual.**

### 2. Debate (sin URL, sesion activa)

```bash
./scripts/run-finanzas-py.sh scripts/intel_youtube.py --debate --text "<mensaje>" --json
```

Debatir: preguntas, contraargumentos, aplicacion a consultoria/producto/contenido Chile.

### 3. Registrar insight

Usuario escribe: `registra insight: <idea>` o `guardar insight: <idea>`

Mismo comando `--debate --text` (el script detecta el prefijo).

## Formato respuesta resumen

```
🎬 YouTube Intel — {titulo}
📌 Puntos clave (1..N)
💡 Insights para ti
🎯 Accionables
───
Debate / registra insight: ...
```

## Reglas

- **Siempre** ejecutar el script; no resumir de memoria ni sin transcript.
- Traducir a espanol si el video esta en ingles.
- Titulos de puntos: compactos (~1 linea).
- Sin subtitulos → informar error claro (`youtube-transcript-api`).
- Tras resumen, sesion queda activa 2h para debate via router intel.

## Dependencia

`youtube-transcript-api` en venv finanzas (`scripts/requirements-finanzas-agent.txt`).

## Aplicar config agente

```bash
python3 scripts/apply_openclaw_intel_config.py
```
