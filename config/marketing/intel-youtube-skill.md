<!-- INTEL_YOUTUBE -->

## YouTube — resumen, debate e insights

Cuando Mauro envie un **link de YouTube** (`youtube.com`, `youtu.be`, shorts):

1. Ejecutar (NO improvisar resumen sin transcript):
   `python3 /home/node/openclaw-mauro/scripts/intel_youtube.py --url "<url>" --summarize --json`
   (Host: `./scripts/run-finanzas-py.sh scripts/intel_youtube.py ...`)
2. Copiar `whatsapp_reply` al chat.
3. Mantener sesion activa 2h para debate (`data/intel_youtube_session.json`).

### Debate y seguimiento

Si el mensaje es seguimiento sobre el ultimo video (sin URL nueva):

`python3 /home/node/openclaw-mauro/scripts/intel_youtube.py --debate --text "<mensaje>" --json`

### Registrar insight manual

Formato usuario: `registra insight: <texto>` o `guardar insight: <texto>`

El script persiste en:
- `data/workspace/marketing/intel/youtube/insights.jsonl`
- `data/workspace/marketing/intel/insights/youtube.md`

### Reglas

- Resumen siempre en **espanol chileno tecnico**.
- Puntos clave: titulos compactos, 3-6 items.
- Conectar con DevOps, IA aplicada, observabilidad, FinOps, MLOps, oportunidades Chile.
- No inventar contenido del video; basarse en transcripcion.
- Si no hay subtitulos: avisar y sugerir otro video o transcripcion manual.
