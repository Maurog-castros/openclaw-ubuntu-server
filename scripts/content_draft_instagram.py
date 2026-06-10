"""Crea borrador Instagram (caption + prompt imagen) pendiente de aprobacion."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import resolve_data_path

DEFAULT_DRAFTS = "data/workspace/marketing/content/drafts/instagram"


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9áéíóúñ]+", "-", text)
    return text.strip("-")[:60] or "post"


def build_image_prompt(topic: str, brief: str) -> str:
    return (
        "Infografia profesional en espanol para Instagram cuadrado 1080x1080, estilo corporativo limpio, "
        f"tema: {topic}. Muestra visualmente casos de uso de agentes de IA en empresas: ventas, soporte, "
        "operaciones, analisis de datos, automatizacion de procesos, integracion con sistemas existentes. "
        "Iconos claros por area, sin texto ilegible, colores azul y rojo sobrios, sin logos de marcas. "
        f"Contexto adicional: {brief[:400]}"
    )


def build_caption(topic: str, brief: str, angle: str) -> str:
    hook = angle.strip() or f"Lo que los agentes de IA ya hacen en empresas reales (mas alla del hype)"
    body = (
        f"{hook}\n\n"
        "No es magia ni prompts sueltos: es orquestacion con datos, permisos y metricas.\n\n"
        "En la practica veo equipos usando agentes para:\n"
        "• Responder y clasificar tickets con contexto del negocio\n"
        "• Preparar reportes y conciliaciones (finanzas/ops)\n"
        "• Buscar en documentacion interna y proponer pasos\n"
        "• Automatizar tareas repetitivas entre APIs\n\n"
        f"{brief[:500]}\n\n"
        "Si lideras tecnologia u operaciones: ¿que proceso delegarias primero a un agente con trazabilidad?\n\n"
        "#AgentesIA #IAempresarial #DevOps #Automatizacion #TransformacionDigital"
    )
    return body.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Borrador Instagram pendiente de aprobacion.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--brief", default="", help="Texto del brief Intel o investigacion.")
    parser.add_argument("--angle", default="", help="Hook / angulo opcional.")
    parser.add_argument("--slug", default="")
    parser.add_argument("--drafts-dir", default=DEFAULT_DRAFTS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    drafts_dir = resolve_data_path(args.drafts_dir)
    drafts_dir.mkdir(parents=True, exist_ok=True)
    slug = args.slug or slugify(args.topic)
    today = date.today().isoformat()
    path = drafts_dir / f"{today}-{slug}.md"

    image_prompt = build_image_prompt(args.topic, args.brief)
    caption = build_caption(args.topic, args.brief, args.angle)
    content = f"""---
formato: instagram
estado: pending_approval
fecha: {today}
tema: {args.topic}
canal: instagram
fuente_intel: reports
---

# Borrador Instagram — {args.topic}

## Imagen (generar y adjuntar al usuario)

{image_prompt}

## Caption (copiar al publicar)

{caption}

## Aprobacion

Responde **APROBADO** para marcar listo (publicacion manual por Mauro).
Responde con cambios y regenera caption/imagen si hace falta.
"""
    path.write_text(content, encoding="utf-8")
    summary = (
        f"Borrador Instagram guardado: {path.name}\n"
        f"Estado: pending_approval\n\n"
        f"Caption (preview):\n{caption[:900]}{'…' if len(caption) > 900 else ''}\n\n"
        f"Prompt imagen:\n{image_prompt[:500]}…"
    )
    payload: Dict[str, Any] = {
        "status": "pending_approval",
        "path": str(path),
        "topic": args.topic,
        "caption": caption,
        "image_prompt": image_prompt,
        "summary": summary,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(summary)


if __name__ == "__main__":
    main()
