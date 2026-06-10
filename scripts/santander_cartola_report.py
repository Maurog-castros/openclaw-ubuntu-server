"""Reporte compacto de cartolas Santander procesadas."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Dict, List


def read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def cartola_key(row: Dict[str, str]) -> str:
    return row.get("message_id") or row.get("pdf_filename") or row.get("period_to") or "desconocida"


def expected_months(from_date: str) -> List[str]:
    try:
        start_year, start_month, _ = [int(part) for part in from_date.split("-")]
    except ValueError:
        return []
    today = date.today()
    end_year, end_month = today.year, today.month - 1
    if end_month == 0:
        end_year -= 1
        end_month = 12
    months: List[str] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return months


def summarize(path: Path, from_date: str) -> Dict[str, Any]:
    rows = read_rows(path)
    filtered = [r for r in rows if (r.get("movement_date") or r.get("period_to") or "") >= from_date]
    cartolas: Dict[str, Dict[str, Any]] = {}
    month_counts: Counter[str] = Counter()

    for row in filtered:
        key = cartola_key(row)
        period_to = row.get("period_to") or ""
        period_from = row.get("period_from") or ""
        movement_date = row.get("movement_date") or ""
        month = (period_to or movement_date)[:7]
        if month:
            month_counts[month] += 1
        item = cartolas.setdefault(
            key,
            {
                "message_id": row.get("message_id") or "",
                "pdf_filename": row.get("pdf_filename") or "",
                "period_from": period_from,
                "period_to": period_to,
                "movements": 0,
            },
        )
        item["movements"] += 1
        if period_from and (not item.get("period_from") or period_from < item["period_from"]):
            item["period_from"] = period_from
        if period_to and (not item.get("period_to") or period_to > item["period_to"]):
            item["period_to"] = period_to

    items = sorted(cartolas.values(), key=lambda x: (x.get("period_to") or "", x.get("pdf_filename") or ""))
    months = sorted({(i.get("period_to") or "")[:7] for i in items if i.get("period_to")})
    expected = expected_months(from_date)
    missing_months = [month for month in expected if month not in months]
    reply_lines = [
        f"Cartolas Santander desde {from_date}:",
        f"Cartolas procesadas: {len(items)}",
        f"Movimientos en cartolas: {len(filtered)}",
    ]
    if months:
        reply_lines.append("Meses cubiertos: " + ", ".join(months))
    if missing_months:
        reply_lines.append("Meses esperados sin cartola: " + ", ".join(missing_months))
        reply_lines.append("Causa probable: no existe correo/PDF Cartola Mensual en Gmail para esos meses.")
    if items:
        last = items[-1]
        reply_lines.append(
            f"Ultima cartola: {last.get('period_from') or '?'} a {last.get('period_to') or '?'} ({last.get('movements')} mov.)"
        )
    return {
        "status": "ok",
        "from_date": from_date,
        "cartolas_count": len(items),
        "movements_count": len(filtered),
        "months": months,
        "expected_months": expected,
        "missing_months": missing_months,
        "cartolas": items,
        "summary": "\n".join(reply_lines),
        "whatsapp_reply": "\n".join(reply_lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Cuenta cartolas Santander procesadas.")
    parser.add_argument("--cartola", default="data/santander_cartola.csv")
    parser.add_argument("--from-date", default="2026-01-01")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = summarize(Path(args.cartola), args.from_date)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["summary"])


if __name__ == "__main__":
    main()
