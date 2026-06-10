"""OCR de órdenes/exámenes médicos chilenos con modelo visión."""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from finanzas_common import extract_json_object
from vida_common import reply

load_dotenv()

DEFAULT_VISION_MODEL = os.getenv("OPENCLAW_VISION_MODEL", "qwen3-vl-30b-a3b-instruct")

EXAM_PROMPT = """
Eres OCR experto en documentos médicos chilenos (MINSAL, CESFAM, órdenes de laboratorio).
Responde SOLO JSON válido (sin markdown).

PRIORIDAD para la cita del paciente:
1. Fecha y hora MANUSCRITAS en el documento (arriba, margen, anotaciones) = cita real.
2. Si no hay manuscrito claro, appointment_date y appointment_time = null.

Esquema:
{
  "document_type": "orden_laboratorio|orden_examen|receta|otro",
  "establishment": "CESFAM San Joaquín",
  "establishment_address": "dirección completa",
  "patient_name": "nombre paciente",
  "order_number": "número orden",
  "order_date": "YYYY-MM-DD",
  "appointment_date": "YYYY-MM-DD",
  "appointment_time": "HH:MM",
  "clinical_context": "diagnóstico o motivo",
  "exams": [
    {"code": "0302047", "name": "Glicemia", "details": "detalle si aparece"}
  ]
}

Reglas:
- Fechas chilenas DD/MM/YY o DD/MM/YYYY -> YYYY-MM-DD (año 26 = 2026).
- Hora "7:20 Hrs" -> "07:20" (24h).
- Lista TODOS los exámenes visibles en todas las páginas de la imagen.
- Incluye código entre paréntesis en "code" y nombre en "name".
- "details" = subtítulo o componentes del examen si están impresos.
- No inventes exámenes ni fechas que no estén en el documento.
""".strip()


def openclaw_client() -> OpenAI:
    base_url = os.getenv("OPENCLAW_PRIMARY_URL", "https://ia.iamiko.cl/v1")
    api_key = os.getenv("LITELLM_MASTER_KEY", "sk-openclaw-local")
    return OpenAI(base_url=base_url, api_key=api_key)


def image_to_data_url(image_path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(image_path))
    if not mime:
        mime = "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def parse_date_cl(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", value)
    if not m:
        return None
    d, mo, y = m.groups()
    if len(y) == 2:
        y = f"20{y}"
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def parse_time_cl(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value).strip().lower().replace("hrs", "").replace("hr", "").strip()
    m = re.search(r"(\d{1,2})[:.](\d{2})", value)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = re.search(r"(\d{1,2})\s*h", value)
    if m:
        return f"{int(m.group(1)):02d}:00"
    return None


def normalize_exam_payload(payload: dict[str, Any]) -> dict[str, Any]:
    exams_out = []
    for item in payload.get("exams") or []:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        exams_out.append(
            {
                "code": str(item.get("code") or "").strip(),
                "name": name,
                "details": str(item.get("details") or "").strip(),
            }
        )
    return {
        "document_type": str(payload.get("document_type") or "otro").strip(),
        "establishment": str(payload.get("establishment") or "").strip(),
        "establishment_address": str(payload.get("establishment_address") or "").strip(),
        "patient_name": str(payload.get("patient_name") or "").strip(),
        "order_number": str(payload.get("order_number") or "").strip(),
        "order_date": parse_date_cl(payload.get("order_date")),
        "appointment_date": parse_date_cl(payload.get("appointment_date")),
        "appointment_time": parse_time_cl(payload.get("appointment_time")),
        "clinical_context": str(payload.get("clinical_context") or "").strip(),
        "exams": exams_out,
    }


def call_vision(image_path: Path, model: str) -> dict[str, Any]:
    client = openclaw_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": EXAM_PROMPT},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
                ],
            }
        ],
        temperature=0.05,
    )
    content = response.choices[0].message.content or ""
    return normalize_exam_payload(extract_json_object(content))


def apply_text_hints(data: dict[str, Any], text: str) -> dict[str, Any]:
    if not text:
        return data
    date_m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", text)
    time_m = re.search(r"(\d{1,2})[:.](\d{2})", text)
    if date_m and not data.get("appointment_date"):
        data["appointment_date"] = parse_date_cl(date_m.group(0))
    if time_m and not data.get("appointment_time"):
        data["appointment_time"] = parse_time_cl(time_m.group(0))
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--text", default="")
    ap.add_argument("--model", default=DEFAULT_VISION_MODEL)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        out = reply(f"No encuentro la imagen: {image_path}", status="error")
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])
        return

    try:
        data = call_vision(image_path, args.model)
        data = apply_text_hints(data, args.text)
        out = reply("OCR de examen listo.", parsed=data, status="ok")
    except Exception as exc:
        out = reply(f"No pude leer la orden médica: {exc}", status="error")

    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
