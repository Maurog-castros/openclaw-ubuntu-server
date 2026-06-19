"""Listado compacto de boletas procesadas (evita volcar el CSV en el chat)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import (
    DEFAULT_OBSERVACIONES,
    DEFAULT_UNIFIED_CSV,
    load_observaciones,
    parse_clp,
    resolve_data_path,
)
from finanzas_merchant_report import fmt_clp, fmt_date_dd_mm_yy, load_all_rows
from finanzas_receipt_caption import (
    display_merchant_name,
    looks_like_bank_screenshot,
    looks_like_equal_split,
)

RECEIPT_SOURCES = frozenset(
    {"lider_gmail", "telegram_foto", "whatsapp_foto", "openclaw_web", "manual"}
)
SOURCE_LABEL = {
    "lider_gmail": "Gmail Lider",
    "telegram_foto": "Foto Telegram",
    "whatsapp_foto": "Foto WhatsApp",
    "openclaw_web": "Web",
    "manual": "Manual",
}


def receipt_group_key(row: Dict[str, str]) -> Tuple[str, ...]:
    ref = (row.get("reference_id") or row.get("document_number") or row.get("movement_id") or "").strip()
    return (
        ref,
        (row.get("movement_date") or "")[:10],
        str(row.get("ticket_total") or "").strip(),
        (row.get("merchant") or row.get("merchant_branch") or "").strip().lower(),
        (row.get("source") or "").strip(),
    )


def group_receipts(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    buckets: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for row in rows:
        if (row.get("movement_type") or "") != "gasto":
            continue
        source = (row.get("source") or "").strip()
        if source not in RECEIPT_SOURCES:
            continue
        key = receipt_group_key(row)
        bucket = buckets.get(key)
        if not bucket:
            merchant = (row.get("merchant") or "").strip()
            branch = (row.get("merchant_branch") or "").strip()
            store = display_merchant_name(merchant, branch)
            ticket_total = parse_clp(row.get("ticket_total") or row.get("amount_clp") or "0") or 0
            bucket = {
                "store": store or "desconocido",
                "purchase_date": (row.get("movement_date") or "")[:10],
                "processed_at": row.get("processed_at") or "",
                "ticket_total": ticket_total,
                "source": source,
                "receipt_number": (row.get("document_number") or "").strip(),
                "items": [],
                "movement_ids": [],
            }
            buckets[key] = bucket
        desc = (row.get("description") or "").strip()
        amount = parse_clp(row.get("amount_clp") or "0") or 0
        mid = (row.get("movement_id") or "").strip()
        if mid and mid not in bucket["movement_ids"]:
            bucket["movement_ids"].append(mid)
        if desc and not any(i.get("product") == desc for i in bucket["items"]):
            bucket["items"].append({"product": desc, "amount": amount})
        if row.get("processed_at", "") > bucket.get("processed_at", ""):
            bucket["processed_at"] = row["processed_at"]

    grouped = list(buckets.values())
    filtered: List[Dict[str, Any]] = []
    for receipt in grouped:
        pseudo = {
            "store": receipt.get("store"),
            "ticket_total": receipt.get("ticket_total"),
            "items": receipt.get("items") or [],
        }
        if looks_like_bank_screenshot(pseudo):
            continue
        filtered.append(receipt)

    filtered.sort(
        key=lambda item: (
            item.get("processed_at") or "",
            item.get("purchase_date") or "",
        ),
        reverse=True,
    )
    return filtered


def should_show_item_amounts(items: List[Dict[str, Any]], ticket_total: int) -> bool:
    if len(items) <= 1:
        return True
    amounts = [int(i.get("amount") or 0) for i in items]
    if ticket_total and sum(amounts) != ticket_total:
        return False
    return not looks_like_equal_split(items, ticket_total)


def format_item_amount(item: Dict[str, Any], *, ticket_total: int, items_count: int) -> int:
    amount = int(item.get("amount") or 0)
    if items_count == 1 and ticket_total and amount != ticket_total:
        return ticket_total
    return amount


def build_summary(
    receipts: List[Dict[str, Any]],
    *,
    limit: int,
    observations: Dict[str, Dict[str, str]],
    full_detail: bool = False,
) -> str:
    if not receipts:
        return "No hay boletas procesadas en el CSV unificado."

    shown = receipts[:limit]
    lines = [f"Ultimas {len(shown)} boleta(s) procesada(s):"]
    for idx, receipt in enumerate(shown, start=1):
        when = fmt_date_dd_mm_yy(receipt.get("purchase_date") or "")
        if not when or when == "?":
            when = (receipt.get("processed_at") or "")[:10] or "?"
        source = SOURCE_LABEL.get(receipt.get("source") or "", receipt.get("source") or "?")
        total = int(receipt.get("ticket_total") or 0)
        store = receipt.get("store") or "desconocido"
        doc = receipt.get("receipt_number") or ""
        doc_part = f" N° {doc}" if doc else ""
        lines.append(f"{idx}. {when} — {store}{doc_part} — {fmt_clp(total)} [{source}]")

        note = ""
        for mid in receipt.get("movement_ids") or []:
            note = (observations.get(mid, {}) or {}).get("note", "").strip()
            if note:
                break
        if note:
            lines.append(f"   Nota: {note}")

        items = receipt.get("items") or []
        if len(items) == 1 and items[0].get("product") == "boleta_sin_detalle_detectado":
            lines.append("   (sin detalle OCR)")
        elif items:
            show_amounts = should_show_item_amounts(items, total)
            if not show_amounts:
                product_items = items if full_detail else items[:6]
                products = ", ".join(i.get("product") or "item" for i in product_items)
                lines.append(f"   - {products}")
                if not full_detail and len(items) > 6:
                    lines.append(f"   ... +{len(items) - 6} items")
            else:
                preview = items if full_detail else items[:4]
                for item in preview:
                    amt = format_item_amount(item, ticket_total=total, items_count=len(items))
                    lines.append(f"   - {item.get('product') or 'item'} — {fmt_clp(amt)}")
                if not full_detail and len(items) > 4:
                    lines.append(f"   ... +{len(items) - 4} items")
    if len(receipts) > limit:
        lines.append(f"(Total registradas: {len(receipts)}; mostrando {limit})")
    return "\n".join(lines)


def filter_by_merchant(receipts: List[Dict[str, Any]], merchant: str) -> List[Dict[str, Any]]:
    needle = (merchant or "").strip().lower()
    if not needle:
        return receipts
    return [
        receipt
        for receipt in receipts
        if needle in str(receipt.get("store") or "").lower()
        or needle in str(receipt.get("source") or "").lower()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Boletas procesadas recientes.")
    parser.add_argument("--csv", default=DEFAULT_UNIFIED_CSV)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--merchant", default="")
    parser.add_argument("--full-detail", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    csv_path = resolve_data_path(args.csv)
    if not csv_path.exists():
        payload = {
            "status": "error",
            "message": f"CSV no encontrado: {csv_path}",
            "summary": "No pude leer finanzas_movimientos.csv.",
            "whatsapp_reply": "No pude leer el archivo de movimientos (CSV no montado).",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["summary"])
        sys.exit(1)

    rows = load_all_rows(csv_path)
    observations = load_observaciones(resolve_data_path(DEFAULT_OBSERVACIONES))
    receipts = filter_by_merchant(group_receipts(rows), args.merchant)
    limit = max(args.limit, 1)
    if not receipts:
        if args.merchant:
            summary = f"No encontré boletas registradas para {args.merchant}."
        else:
            summary = "Aún no tienes boletas registradas.\nEnvía una foto de boleta o escribe */fin* para empezar."
        payload = {
            "status": "ok",
            "receipt_count": 0,
            "shown": 0,
            "receipts": [],
            "summary": summary,
            "whatsapp_reply": summary,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else summary)
        return
    summary = build_summary(receipts, limit=limit, observations=observations, full_detail=args.full_detail)
    payload = {
        "status": "ok",
        "receipt_count": len(receipts),
        "shown": min(len(receipts), limit),
        "receipts": receipts[:limit],
        "summary": summary,
        "whatsapp_reply": summary,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(summary)


if __name__ == "__main__":
    main()
