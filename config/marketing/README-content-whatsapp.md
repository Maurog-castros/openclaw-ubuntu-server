# Content + WhatsApp (Instagram con aprobacion)

## Flujo

1. Escribes por WhatsApp (vía agente **finanzas** que redirige, o mensaje de contenido).
2. **Intel** aporta tendencias (`intel/reports/` + opcional agente intel).
3. **Content (Drift)** genera borrador + imagen.
4. Te muestra caption e imagen → respondes **APROBADO** o pides cambios.
5. No se publica en Instagram automaticamente.

## Comandos utiles

```text
/content haz una publicacion sobre agentes ia en instagram...
```

O sin prefijo, si el mensaje es claramente de redes (finanzas lo redirige a content).

Finanzas explicito:

```text
/fin cuanto gaste en mayo
```

## Aplicar config en servidor

```bash
cd /home/mauro/openclaw-mauro
python3 scripts/apply_openclaw_content_config.py
cd openclaw && docker compose -f docker-compose.yml -f docker-compose.finanzas-mounts.yml up -d openclaw-gateway
```

## Scripts

| Script | Uso |
|--------|-----|
| `content_intel_brief.py --topic "agentes ia" --json` | Lee reportes Intel |
| `content_draft_instagram.py --topic "..." --brief "..." --json` | Borrador + prompt imagen |

Borradores: `data/workspace/marketing/content/drafts/instagram/`

## Inspiracion desde un post existente

> Revisa este post de Instagram https://www.instagram.com/p/XXXX/

El agente ejecuta `content_instagram_analyze.py` (descarga imagen + caption + vision) y propone adaptacion estilo Mauro.

Referencias guardadas en `data/workspace/marketing/content/references/instagram/`.

## Ejemplo WhatsApp

> haz un publicacion sobre agentes ia en instagram, que tenga imagen de todo lo que los agentes pueden ayudar en una empresa

Respuesta esperada: investigacion → borrador → imagen → «Pendiente tu aprobacion».
