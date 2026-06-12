"""Procesa fotos de boletas con modelo vision y las guarda en CSV."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import mimetypes
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import (
    DEFAULT_RECEIPTS_REGISTRY,
    DEFAULT_UNIFIED_CSV,
    DEFAULT_VISION_CSV,
    VISION_CSV_COLUMNS,
    category_for_product,
    ensure_csv_headers,
    extract_json_object,
    file_sha256,
    find_receipt_duplicate,
    fingerprint_from_receipt_dict,
    is_image_processed,
    load_receipt_registry,
    merge_all_sources,
    parse_clp,
    register_image_hash,
    register_receipt_fingerprint,
    save_receipt_registry,
    seed_registry_from_csvs,
)
from finanzas_receipt_caption import enrich_receipt_from_caption, looks_like_bank_screenshot


class VisionModelUnsupportedError(RuntimeError):
    """Raised when the configured model rejects image inputs."""

load_dotenv()

DEFAULT_VISION_MODEL = os.getenv(
    "OPENCLAW_VISION_MODEL",
    "qwen3-vl-30b-a3b-instruct",
)
DEFAULT_INBOX = Path("data/inbox/boletas")
DEFAULT_PROCESSED = Path("data/inbox/boletas/processed")
DEFAULT_STATE = Path("data/receipts_vision_state.json")
DEFAULT_REGISTRY = Path(DEFAULT_RECEIPTS_REGISTRY)
DEFAULT_INBOUND_TELEGRAM = Path("data/config/media/inbound")
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"})

RECEIPT_PROMPT = """
Eres OCR experto en boletas/facturas chilenas (SII). Responde SOLO JSON valido (sin markdown).

Formato tipico farmacia/supermercado:
- Linea precio: "1 x 6480" o "2 x 3590"
- Codigo SKU: CH4052, 2063360000002
- Descripcion producto en linea siguiente o misma linea
- Total linea al final: "6.480" o "6480" (punto = miles CLP)

Esquema:
{
  "store": "nombre comercio",
  "store_branch": "sucursal o direccion",
  "merchant_rut": "76.636.728-3",
  "receipt_number": "2041522",
  "purchase_date": "YYYY-MM-DD",
  "purchase_time": "HH:MM:SS",
  "payment_method": "efectivo|tarjeta|transferencia|desconocido",
  "ticket_total": 16840,
  "items": [
    {"product": "nombre completo producto", "quantity": 1, "amount": 6480, "category": "salud_farmacia"}
  ]
}

Reglas CRITICAS:
- Montos enteros CLP sin simbolo $. "16.840" -> 16840.
- Incluye CADA producto de la seccion detalle. No omitas lineas.
- La suma de items[].amount DEBE igualar ticket_total.
- Si hay 4 productos en papel, items debe tener 4 entradas.
- Nombre producto completo (dosis, caps, gr) si visible.
- Fecha DD/MM/YYYY en boleta -> YYYY-MM-DD.
""".strip()

RECEIPT_RETRY_PROMPT = """
Tu JSON anterior omitio productos o la suma no cuadra con el TOTAL impreso.
Relee la imagen completa. Incluye TODAS las lineas de producto visibles.
Verifica: sum(items[].amount) == ticket_total.
Responde SOLO JSON corregido, sin markdown.
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


def normalize_receipt_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    purchase_date = str(payload.get("purchase_date") or "").strip()
    purchase_time = str(payload.get("purchase_time") or "").strip()
    purchase_datetime = str(payload.get("purchase_datetime") or "").strip()
    if not purchase_datetime and purchase_date:
        purchase_datetime = f"{purchase_date} {purchase_time}".strip()

    items_out: List[Dict[str, Any]] = []
    for item in payload.get("items") or []:
        product = str(item.get("product") or item.get("name") or "").strip()
        if not product:
            continue
        amount = parse_clp(item.get("amount") or item.get("line_amount"))
        category = str(item.get("category") or category_for_product(product))
        items_out.append(
            {
                "product": product,
                "quantity": item.get("quantity") or 1,
                "amount": amount,
                "category": category,
            }
        )

    ticket_total = parse_clp(payload.get("ticket_total"))
    if not items_out and ticket_total:
        items_out = [{"product": "boleta_sin_detalle_detectado", "quantity": 1, "amount": ticket_total, "category": "otros"}]

    ticket_total = parse_clp(payload.get("ticket_total"))
    if not items_out and ticket_total:
        items_out = [{"product": "boleta_sin_detalle_detectado", "quantity": 1, "amount": ticket_total, "category": "otros"}]

    result = {
        "store": str(payload.get("store") or "").strip(),
        "store_branch": str(payload.get("store_branch") or "").strip(),
        "merchant_rut": str(payload.get("merchant_rut") or "").strip(),
        "receipt_number": str(payload.get("receipt_number") or "").strip(),
        "purchase_date": purchase_date,
        "purchase_time": purchase_time,
        "purchase_datetime": purchase_datetime,
        "payment_method": str(payload.get("payment_method") or "desconocido").strip(),
        "ticket_total": ticket_total,
        "items": items_out,
    }
    result["validation"] = validate_receipt_payload(result)
    return result


def validate_receipt_payload(receipt: Dict[str, Any]) -> Dict[str, Any]:
    items = receipt.get("items") or []
    ticket_total = parse_clp(receipt.get("ticket_total"))
    line_amounts = [parse_clp(item.get("amount")) for item in items]
    line_amounts_clean = [amount for amount in line_amounts if amount is not None]
    items_sum = sum(line_amounts_clean) if line_amounts_clean else None

    issues: List[str] = []
    if ticket_total is None or ticket_total <= 0:
        issues.append("total_invalido")
    if len(items) == 0:
        issues.append("sin_items")
    if items_sum is not None and ticket_total is not None and items_sum != ticket_total:
        issues.append(f"suma_items_{items_sum}_distinta_total_{ticket_total}")

    return {
        "ok": len(issues) == 0,
        "items_count": len(items),
        "items_sum": items_sum,
        "ticket_total": ticket_total,
        "issues": issues,
    }


def receipt_needs_retry(receipt: Dict[str, Any]) -> bool:
    validation = receipt.get("validation") or {}
    if not validation.get("ok"):
        return True
    issues = validation.get("issues") or []
    return any("suma_items" in issue or issue in {"sin_items", "total_invalido"} for issue in issues)


def call_vision_model(
    client: OpenAI,
    model: str,
    image_path: Path,
    prompt: str,
    prior_assistant: Optional[str] = None,
) -> str:
    user_content: List[Any] = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
    ]
    messages: List[Dict[str, Any]] = [{"role": "user", "content": user_content}]
    if prior_assistant:
        messages.extend(
            [
                {"role": "assistant", "content": prior_assistant},
                {"role": "user", "content": RECEIPT_RETRY_PROMPT},
            ]
        )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.05,
        )
    except BadRequestError as exc:
        message = str(exc)
        if "does not support image" in message or "contain images" in message:
            raise VisionModelUnsupportedError(f"Modelo no soporta imagenes: {model}") from exc
        raise
    return response.choices[0].message.content or ""


def extract_receipt_from_image(image_path: Path, model: str) -> Dict[str, Any]:
    client = openclaw_client()
    content = call_vision_model(client, model, image_path, RECEIPT_PROMPT)
    receipt = normalize_receipt_payload(extract_json_object(content))
    if receipt_needs_retry(receipt):
        retry_content = call_vision_model(client, model, image_path, RECEIPT_PROMPT, prior_assistant=content)
        retry_receipt = normalize_receipt_payload(extract_json_object(retry_content))
        if not receipt_needs_retry(retry_receipt) or len(retry_receipt.get("items") or []) >= len(
            receipt.get("items") or []
        ):
            receipt = retry_receipt
    return receipt


def format_receipt_summary(receipt: Dict[str, Any]) -> str:
    lines = [
        f"Comercio: {receipt.get('store') or 'desconocido'}",
        f"Fecha: {receipt.get('purchase_datetime') or receipt.get('purchase_date') or '-'}",
        f"Boleta N°: {receipt.get('receipt_number') or '-'}",
        f"Total: ${receipt.get('ticket_total') or 0:,}".replace(",", "."),
        f"Pago: {receipt.get('payment_method') or '-'}",
        "Items:",
    ]
    for idx, item in enumerate(receipt.get("items") or [], start=1):
        amount = parse_clp(item.get("amount")) or 0
        lines.append(f"  {idx}. {item.get('product')} — ${amount:,}".replace(",", "."))
    validation = receipt.get("validation") or {}
    if not validation.get("ok"):
        lines.append(f"Advertencia OCR: {', '.join(validation.get('issues') or [])}")
    return "\n".join(lines)


def find_latest_inbound_image(inbound_dir: Path) -> Optional[Path]:
    if not inbound_dir.exists():
        return None
    candidates = [
        path
        for path in inbound_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def infer_inbound_source(inbound_dir: Path) -> str:
    """Heuristica: mismo directorio media/inbound para Telegram y WhatsApp."""
    lowered = str(inbound_dir).lower()
    if "whatsapp" in lowered:
        return "whatsapp_foto"
    return "telegram_foto"


def vision_rows_for_csv(
    receipt: Dict[str, Any],
    *,
    source: str,
    source_ref: str,
    image_path: str,
    image_hash: str,
    model_used: str,
) -> List[List[Any]]:
    processed_at = datetime.now().isoformat(timespec="seconds")
    rows: List[List[Any]] = []
    items = receipt.get("items") or []
    if not items:
        items = [{"product": "boleta_sin_detalle_detectado", "amount": receipt.get("ticket_total"), "category": "otros"}]

    for item in items:
        product = item.get("product") or "item_sin_nombre"
        rows.append(
            [
                processed_at,
                source,
                source_ref,
                image_path,
                image_hash,
                receipt.get("purchase_date") or "",
                receipt.get("purchase_time") or "",
                receipt.get("purchase_datetime") or "",
                receipt.get("store") or "",
                receipt.get("store_branch") or "",
                receipt.get("merchant_rut") or "",
                receipt.get("receipt_number") or "",
                product,
                item.get("category") or category_for_product(product),
                item.get("amount") or "",
                receipt.get("ticket_total") or "",
                receipt.get("payment_method") or "",
                model_used,
            ]
        )
    return rows


def append_vision_rows(csv_file: Path, rows: List[List[Any]]) -> None:
    if not rows:
        return
    ensure_csv_headers(csv_file, VISION_CSV_COLUMNS)
    with csv_file.open("a", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def load_registry(registry_file: Path, legacy_state_file: Path) -> Dict[str, Any]:
    registry = load_receipt_registry(registry_file, legacy_state_file=legacy_state_file)
    return registry


def finalize_skipped_image(
    image_path: Path,
    image_hash: str,
    registry: Dict[str, Any],
    registry_file: Path,
    legacy_state_file: Path,
    processed_dir: Optional[Path],
    result: Dict[str, Any],
) -> Dict[str, Any]:
    register_image_hash(registry, image_hash)
    save_receipt_registry(registry_file, registry)
    legacy_state_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_state_file.write_text(
        json.dumps(registry.get("image_hashes", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if processed_dir and image_path.exists():
        processed_dir.mkdir(parents=True, exist_ok=True)
        target = processed_dir / f"{image_hash[:12]}_{image_path.name}"
        if image_path.resolve().parent != processed_dir.resolve():
            shutil.move(str(image_path), str(target))
    return result


def process_image_file(
    image_path: Path,
    *,
    output_csv: Path,
    state_file: Path,
    registry_file: Path,
    model: str,
    source: str,
    source_ref: str,
    processed_dir: Optional[Path],
    merge_unified: bool,
    unified_csv: Path,
    lider_csv: Path,
    transferencias_csv: Path,
    owner_rut: str,
    user_caption: str = "",
) -> Dict[str, Any]:
    if not image_path.exists():
        raise FileNotFoundError(f"No existe imagen: {image_path}")
    if image_path.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError(f"Formato no soportado: {image_path.suffix}")

    image_hash = file_sha256(image_path)
    registry = load_registry(registry_file, state_file)
    seed_registry_from_csvs(
        registry,
        vision_csv=output_csv,
        lider_csv=lider_csv,
        unified_csv=unified_csv if unified_csv.exists() else None,
    )

    if is_image_processed(registry, image_hash):
        return finalize_skipped_image(
            image_path,
            image_hash,
            registry,
            registry_file,
            state_file,
            processed_dir,
            {"status": "skipped", "reason": "duplicate_image", "image_hash": image_hash},
        )

    try:
        receipt = extract_receipt_from_image(image_path, model=model)
    except VisionModelUnsupportedError as exc:
        return {
            "status": "skipped",
            "reason": "vision_model_unsupported",
            "image_hash": image_hash,
            "model": model,
            "message": str(exc),
        }
    if user_caption:
        receipt = enrich_receipt_from_caption(receipt, user_caption)
    if looks_like_bank_screenshot(receipt):
        return finalize_skipped_image(
            image_path,
            image_hash,
            registry,
            registry_file,
            state_file,
            processed_dir,
            {
                "status": "rejected",
                "reason": "bank_screenshot",
                "message": (
                    "Esa imagen parece un extracto de movimientos bancarios, no una boleta. "
                    "Para saldo usa captura de la app Santander; para movimientos pregunta transferencias."
                ),
                "image_hash": image_hash,
                "parsed": {
                    "store": receipt.get("store"),
                    "ticket_total": receipt.get("ticket_total"),
                    "items_count": len(receipt.get("items") or []),
                },
            },
        )
    fingerprint = fingerprint_from_receipt_dict(receipt)
    duplicate = find_receipt_duplicate(registry, fingerprint)
    if duplicate:
        return finalize_skipped_image(
            image_path,
            image_hash,
            registry,
            registry_file,
            state_file,
            processed_dir,
            {
                "status": "skipped",
                "reason": "duplicate_receipt",
                "image_hash": image_hash,
                "receipt_fingerprint": fingerprint,
                "existing": duplicate,
                "parsed": {
                    "store": receipt.get("store"),
                    "receipt_number": receipt.get("receipt_number"),
                    "purchase_date": receipt.get("purchase_date"),
                    "ticket_total": receipt.get("ticket_total"),
                },
            },
        )

    rows = vision_rows_for_csv(
        receipt,
        source=source,
        source_ref=source_ref or image_hash[:12],
        image_path=str(image_path),
        image_hash=image_hash,
        model_used=model,
    )
    append_vision_rows(output_csv, rows)
    register_image_hash(registry, image_hash)
    if fingerprint:
        register_receipt_fingerprint(
            registry,
            fingerprint,
            store=receipt.get("store") or "",
            receipt_number=receipt.get("receipt_number") or "",
            merchant_rut=receipt.get("merchant_rut") or "",
            purchase_date=receipt.get("purchase_date") or "",
            ticket_total=receipt.get("ticket_total"),
            source=source,
            image_hash=image_hash,
        )
    save_receipt_registry(registry_file, registry)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(registry.get("image_hashes", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if processed_dir:
        processed_dir.mkdir(parents=True, exist_ok=True)
        target = processed_dir / f"{image_hash[:12]}_{image_path.name}"
        if image_path.resolve().parent != processed_dir.resolve():
            shutil.move(str(image_path), str(target))

    merge_stats = None
    if merge_unified:
        merge_stats = merge_all_sources(
            unified_csv=unified_csv,
            lider_csv=lider_csv,
            vision_csv=output_csv,
            transferencias_csv=transferencias_csv,
            owner_rut=owner_rut,
            registry_file=registry_file,
        )

    return {
        "status": "processed",
        "image_hash": image_hash,
        "receipt_fingerprint": fingerprint,
        "store": receipt.get("store"),
        "ticket_total": receipt.get("ticket_total"),
        "items_count": len(receipt.get("items") or []),
        "items": receipt.get("items") or [],
        "validation": receipt.get("validation"),
        "summary": format_receipt_summary(receipt),
        "rows_written": len(rows),
        "merge": merge_stats,
    }


def process_inbox_folder(
    inbox_dir: Path,
    processed_dir: Path,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not inbox_dir.exists():
        inbox_dir.mkdir(parents=True, exist_ok=True)
        return results

    for image_path in sorted(inbox_dir.iterdir()):
        if not image_path.is_file():
            continue
        if image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        result = process_image_file(
            image_path,
            processed_dir=processed_dir,
            source=kwargs.get("source", "telegram_foto"),
            source_ref=kwargs.get("source_ref", ""),
            **{k: v for k, v in kwargs.items() if k not in {"source", "source_ref"}},
        )
        results.append({"file": str(image_path), **result})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Procesa boletas en foto con modelo vision.")
    parser.add_argument("--image", help="Ruta a una imagen de boleta.")
    parser.add_argument(
        "--latest-inbound",
        action="store_true",
        help="Procesa la foto mas reciente en data/config/media/inbound (Telegram).",
    )
    parser.add_argument(
        "--inbound-dir",
        default=str(DEFAULT_INBOUND_TELEGRAM),
        help="Carpeta inbound Telegram para --latest-inbound.",
    )
    parser.add_argument("--inbox", default=str(DEFAULT_INBOX), help="Carpeta inbox para fotos nuevas.")
    parser.add_argument(
        "--processed-dir",
        default=str(DEFAULT_PROCESSED),
        help="Donde mover imagenes ya procesadas.",
    )
    parser.add_argument("--output", default=DEFAULT_VISION_CSV, help="CSV intermedio de vision.")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="Legacy estado hash imagen.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY), help="Registro dedup boletas.")
    parser.add_argument("--model", default=DEFAULT_VISION_MODEL, help="Modelo vision en Iamiko.")
    parser.add_argument(
        "--source",
        default="telegram_foto",
        choices=["telegram_foto", "whatsapp_foto", "openclaw_web", "manual"],
        help="Origen del documento.",
    )
    parser.add_argument("--source-ref", default="", help="ID mensaje Telegram u otra referencia.")
    parser.add_argument("--user-caption", default="", help="Texto del usuario junto a la foto (productos).")
    parser.add_argument("--merge", action="store_true", help="Regenera CSV unificado al terminar.")
    parser.add_argument("--unified-output", default=DEFAULT_UNIFIED_CSV)
    parser.add_argument("--lider-input", default="data/lider_receipts.csv")
    parser.add_argument("--transferencias-input", default="data/transferencias.csv")
    parser.add_argument("--owner-rut", default=os.getenv("FINANZAS_OWNER_RUT", ""))
    parser.add_argument("--json", action="store_true", help="Imprime resultado en JSON.")
    args = parser.parse_args()

    processed_dir = Path(args.processed_dir) if args.processed_dir else None
    common_kwargs = {
        "output_csv": Path(args.output),
        "state_file": Path(args.state),
        "registry_file": Path(args.registry),
        "model": args.model,
        "merge_unified": args.merge,
        "unified_csv": Path(args.unified_output),
        "lider_csv": Path(args.lider_input),
        "transferencias_csv": Path(args.transferencias_input),
        "owner_rut": args.owner_rut,
    }

    if args.image:
        result = process_image_file(
            Path(args.image),
            source=args.source,
            source_ref=args.source_ref,
            processed_dir=processed_dir,
            user_caption=args.user_caption or "",
            **common_kwargs,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.latest_inbound:
        inbound_dir = Path(args.inbound_dir)
        latest = find_latest_inbound_image(inbound_dir)
        if not latest:
            print(json.dumps({"status": "error", "reason": "no_inbound_image"}, ensure_ascii=False))
            raise SystemExit(1)
        source = args.source if args.source != "telegram_foto" else infer_inbound_source(inbound_dir)
        result = process_image_file(
            latest,
            source=source,
            source_ref=args.source_ref,
            processed_dir=None,
            user_caption=args.user_caption or "",
            **common_kwargs,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    results = process_inbox_folder(
        Path(args.inbox),
        processed_dir or Path(args.processed_dir),
        source=args.source,
        source_ref=args.source_ref,
        **common_kwargs,
    )
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"Imagenes procesadas: {len(results)}")
        for item in results:
            print(f"- {item.get('file')}: {item.get('status')}")


if __name__ == "__main__":
    main()
