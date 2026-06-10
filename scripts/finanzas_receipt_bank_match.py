"""Conciliacion boletas digitales vs cartola Santander por fecha y monto."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import DEFAULT_CARTOLA_CSV, DEFAULT_UNIFIED_CSV, normalize_store_name, parse_clp
from finanzas_merchant_report import fmt_clp, parse_iso_date

RECEIPT_SOURCES = {"lider_gmail", "telegram_foto", "whatsapp_foto", "openclaw_web", "manual"}
BANK_SOURCES = {"santander_cartola", "santander_gmail"}


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def in_range(value: str, start: str, end: str) -> bool:
    if not value:
        return False
    return (not start or value >= start) and (not end or value <= end)


def receipt_group_key(row: Dict[str, str]) -> tuple[str, str, str, int]:
    total = int(parse_clp(row.get("ticket_total") or row.get("amount_clp")) or 0)
    return (
        (row.get("movement_date") or "")[:10],
        normalize_store_name(row.get("merchant") or ""),
        row.get("document_number") or "",
        total,
    )


def receipt_groups(rows: Iterable[Dict[str, str]], start: str, end: str) -> List[Dict[str, Any]]:
    grouped: Dict[tuple[str, str, str, int], Dict[str, Any]] = {}
    item_counts: Dict[tuple[str, str, str, int], int] = defaultdict(int)
    for row in rows:
        if row.get("source") not in RECEIPT_SOURCES:
            continue
        if (row.get("movement_type") or "") != "gasto":
            continue
        movement_date = (row.get("movement_date") or "")[:10]
        if not in_range(movement_date, start, end):
            continue
        key = receipt_group_key(row)
        if key[3] <= 0:
            continue
        item_counts[key] += 1
        grouped.setdefault(
            key,
            {
                "date": key[0],
                "merchant": row.get("merchant") or "",
                "merchant_norm": key[1],
                "document_number": key[2],
                "amount": key[3],
                "source": row.get("source") or "",
                "description_sample": row.get("description") or "",
            },
        )
    out = list(grouped.values())
    for item in out:
        key = (
            item["date"],
            item["merchant_norm"],
            item["document_number"],
            item["amount"],
        )
        item["item_count"] = item_counts[key]
    return sorted(out, key=lambda x: (x["date"], x["amount"]), reverse=True)


def bank_entries(rows: Iterable[Dict[str, str]], start: str, end: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("source") not in BANK_SOURCES:
            continue
        if (row.get("movement_type") or "") not in {"gasto", "transferencia_salida"}:
            continue
        movement_date = (row.get("movement_date") or "")[:10]
        if not in_range(movement_date, start, end):
            continue
        amount = int(parse_clp(row.get("amount_clp") or row.get("ticket_total")) or 0)
        if amount <= 0:
            continue
        entries.append(
            {
                "date": movement_date,
                "amount": amount,
                "description": row.get("description") or "",
                "merchant": row.get("merchant") or "",
                "source": row.get("source") or "",
                "document_number": row.get("document_number") or "",
            }
        )
    return entries


def merchant_score(receipt_merchant: str, bank_text: str) -> int:
    merchant = normalize_store_name(receipt_merchant)
    bank = normalize_store_name(bank_text)
    if not merchant:
        return 0
    if merchant in bank or bank in merchant:
        return 3
    if merchant == "lider" and any(token in bank for token in ("lider", "hiper", "lidercl")):
        return 3
    if "jjp" in merchant and "jjp" in bank:
        return 3
    if any(token in bank for token in ("compra", "tuu", "debito", "tarjeta")):
        return 1
    return 0


def match_receipts(
    receipts: List[Dict[str, Any]],
    bank: List[Dict[str, Any]],
    *,
    window_days: int,
) -> Dict[str, Any]:
    used_bank: set[int] = set()
    matched: List[Dict[str, Any]] = []
    unmatched: List[Dict[str, Any]] = []

    for receipt in receipts:
        receipt_date = parse_iso_date(receipt["date"])
        candidates: List[tuple[int, int, int, Dict[str, Any]]] = []
        for idx, entry in enumerate(bank):
            if idx in used_bank or entry["amount"] != receipt["amount"]:
                continue
            bank_date = parse_iso_date(entry["date"])
            if not receipt_date or not bank_date:
                continue
            days = abs((bank_date - receipt_date).days)
            if days > window_days:
                continue
            score = merchant_score(receipt["merchant"], f"{entry['merchant']} {entry['description']}")
            candidates.append((score, -days, idx, entry))

        if not candidates:
            unmatched.append(receipt)
            continue

        candidates.sort(reverse=True)
        score, neg_days, idx, entry = candidates[0]
        used_bank.add(idx)
        matched.append(
            {
                "receipt_date": receipt["date"],
                "bank_date": entry["date"],
                "days_delta": abs(neg_days),
                "amount": receipt["amount"],
                "merchant": receipt["merchant"],
                "receipt_number": receipt["document_number"],
                "receipt_source": receipt["source"],
                "bank_source": entry["source"],
                "bank_description": entry["description"],
                "confidence": "alta" if score >= 3 else "media",
            }
        )

    matched_total = sum(item["amount"] for item in matched)
    unmatched_total = sum(item["amount"] for item in unmatched)
    lines = [
        "Conciliacion boletas vs Santander",
        f"Boletas: {len(receipts)}",
        f"Matcheadas: {len(matched)} ({fmt_clp(matched_total)})",
        f"Sin match banco: {len(unmatched)} ({fmt_clp(unmatched_total)})",
    ]
    if unmatched:
        lines.extend(["", "Sin match banco:"])
        for item in unmatched[:15]:
            lines.append(
                f"- {item['date']} {fmt_clp(item['amount'])} {item['merchant']} "
                f"doc {item['document_number'] or '?'}"
            )

    return {
        "receipt_count": len(receipts),
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
        "matched_total_clp": matched_total,
        "unmatched_total_clp": unmatched_total,
        "matched": matched,
        "unmatched": unmatched,
        "summary": "\n".join(lines),
        "whatsapp_reply": "\n".join(lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Matchea boletas digitales contra Santander.")
    parser.add_argument("--csv", default=DEFAULT_UNIFIED_CSV)
    parser.add_argument("--cartola-csv", default=DEFAULT_CARTOLA_CSV)
    parser.add_argument("--from", dest="date_from", default="")
    parser.add_argument("--to", dest="date_to", default=date.today().isoformat())
    parser.add_argument("--window-days", type=int, default=5)
    parser.add_argument("--detail", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    unified = read_csv(Path(args.csv))
    cartola_rows = read_csv(Path(args.cartola_csv))
    receipts = receipt_groups(unified, args.date_from, args.date_to)
    bank = bank_entries(unified + cartola_rows, args.date_from, args.date_to)
    result = match_receipts(receipts, bank, window_days=args.window_days)

    if args.json:
        payload = dict(result)
        if not args.detail:
            payload["matched"] = payload["matched"][:15]
            payload["unmatched"] = payload["unmatched"][:15]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(result["summary"])


if __name__ == "__main__":
    main()
