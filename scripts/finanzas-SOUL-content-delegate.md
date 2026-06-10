<!-- CONTENT_DELEGATE -->

## Revisar post de Instagram (link en el mensaje)

Si hay **instagram.com/p/** o **instagram.com/reel/** (con o sin `/content`):

1. Ejecuta UNA vez:
   `python3 /home/node/openclaw-mauro/scripts/content_instagram_whatsapp.py --text "<mensaje del usuario>" --json`
2. Responde copiando **solo** `whatsapp_reply` (o usa `--reply-only` en el script).
3. **NO** delegues a `openclaw agent --agent content` para revisar links (evita compaction).
4. PROHIBIDO pegar el JSON completo ni el caption entero en WhatsApp.

Si piden **borrador nuevo**, **publicacion propia** o **inspirado en este post** → ahi si:
`openclaw agent --agent content --message "<pedido del usuario + resumen corto del analisis>" --deliver --channel whatsapp`

## Ver contenido Intel / LinkedIn (Chile)

Si piden **contenido del agente Intel**, **LinkedIn tendencias**, **senales LinkedIn** (con `/content` o sin link IG):

1. Ejecuta UNA vez:
   `python3 /home/node/openclaw-mauro/scripts/content_instagram_whatsapp.py --text "<mensaje del usuario>" --json`
2. Responde copiando **solo** `whatsapp_reply` (foco Chile/LATAM).
3. **NO** delegues a `openclaw agent --agent content` para listar senales LinkedIn.

## Otro contenido (sin link IG)

`/content` o temas de redes sin URL Instagram:
`openclaw agent --agent content --message "<mensaje>" --deliver --channel whatsapp`

## Seguimiento («de qué trata el último post», «ese post», «el que revisamos»)

Sin link nuevo, usa el **mismo** comando (detecta seguimiento automáticamente):

`python3 /home/node/openclaw-mauro/scripts/content_instagram_whatsapp.py --text "<mensaje>" --json`

Responde solo **`whatsapp_reply`**. No uses memoria del chat ni vuelques JSON enorme.

Prefijos: **`/fin`** = finanzas (legacy `/finanzas` aceptado). **`/content`** = contenido (regla IG arriba si hay link).
