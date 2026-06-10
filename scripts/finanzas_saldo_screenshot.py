"""OCR saldo disponible desde screenshot app Santander."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from openai import OpenAI

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import extract_json_object, parse_clp

load_dotenv()

DEFAULT_VISION_MODEL = os.getenv("OPENCLAW_VISION_MODEL", "qwen3-vl-30b-a3b-instruct")

BALANCE_PROMPT = """
Eres OCR de la app movil Banco Santander Chile. Responde SOLO JSON valido.

IMPORTANTE:
- Lee SOLO el saldo DISPONIBLE principal (numero grande rojo arriba, ej. $103.699).
- NO sumes movimientos de la lista inferior.
- NO uses montos de transferencias ni compras individuales.
- Formato CLP: "103.699" o "$103.699" -> 103699 (entero).

Esquema:
{
  "account_label": "Cuenta Corriente|Cuenta Vista|desconocido",
  "available_balance_clp": 103699,
  "as_of_date": "2026-06-08",
  "confidence": "alta|media|baja"
}

as_of_date: fecha visible en la app (YYYY-MM-DD) o null si no aparece.
Si no ves saldo claro arriba, available_balance_clp: null y confidence: baja.
""".strip()


def openclaw_client() -> OpenAI:
    return OpenAI(
        base_url=os.getenv("OPENCLAW_PRIMARY_URL", "https://ia.iamiko.cl/v1"),
        api_key=os.getenv("LITELLM_MASTER_KEY", "sk-openclaw-local"),
    )


def image_to_data_url(image_path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(image_path))
    if not mime:
        mime = "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def extract_balance(image_path: Path, model: str) -> Dict[str, Any]:
    client = openclaw_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": BALANCE_PROMPT},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
                ],
            }
        ],
        temperature=0.05,
    )
    payload = extract_json_object(response.choices[0].message.content or "")
    balance = parse_clp(payload.get("available_balance_clp"))
    as_of = str(payload.get("as_of_date") or "").strip()[:10]
    return {
        "balance_clp": balance,
        "account_label": payload.get("account_label") or "",
        "confidence": payload.get("confidence") or "",
        "as_of_date": as_of,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR saldo app Santander.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--model", default=DEFAULT_VISION_MODEL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(json.dumps({"status": "error", "message": f"No existe {image_path}"}, ensure_ascii=False))
        raise SystemExit(1)

    result = extract_balance(image_path, args.model)
    if not result.get("balance_clp"):
        payload = {"status": "error", "message": "No se detecto saldo en la imagen.", **result}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    payload = {"status": "ok", **result}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
