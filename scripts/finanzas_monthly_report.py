"""Reporte mensual desde finanzas_movimientos.csv."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import DEFAULT_UNIFIED_CSV, DEFAULT_MOVIMIENTO_LINKS, is_excluded_from_totals, load_movimiento_links, parse_clp, resolve_data_path


def load_rows(csv_path: Path, month: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            date = (row.get("movement_date") or "")[:7]
            if date == month:
                rows.append(row)
    return rows


def summarize(rows: list[dict[str, str]], month: str) -> dict:
    by_category: dict[str, float] = defaultdict(float)
    by_merchant: dict[str, float] = defaultdict(float)
    by_type: dict[str, int] = defaultdict(int)
    by_source: dict[str, int] = defaultdict(int)
    total = 0.0

    for row in rows:
        amount = float(parse_clp(row.get("amount_clp") or row.get("ticket_total") or "0") or 0)
        total += amount
        by_category[row.get("category") or "sin_categoria"] += amount
        merchant = row.get("merchant") or row.get("counterparty") or "desconocido"
        by_merchant[merchant] += amount
        by_type[row.get("movement_type") or "desconocido"] += 1
        by_source[row.get("source") or "desconocido"] += 1

    top_merchants = sorted(by_merchant.items(), key=lambda item: item[1], reverse=True)[:10]
    top_categories = sorted(by_category.items(), key=lambda item: item[1], reverse=True)

    lines = [
        f"=== Finanzas {month} ===",
        f"Movimientos: {len(rows)}",
        f"Total: ${int(total):,} CLP".replace(",", "."),
        "",
        "Por tipo:",
    ]
    for name, count in sorted(by_type.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"- {name}: {count}")

    lines.append("")
    lines.append("Por categoria:")
    for name, amount in top_categories:
        lines.append(f"- {name}: ${int(amount):,} CLP".replace(",", "."))

    lines.append("")
    lines.append("Top comercios:")
    for name, amount in top_merchants:
        lines.append(f"- {name}: ${int(amount):,} CLP".replace(",", "."))

    lines.append("")
    lines.append("Fuentes:")
    for name, count in sorted(by_source.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"- {name}: {count} mov.")

    return {
        "month": month,
        "movement_count": len(rows),
        "total_clp": int(total),
        "by_category": {k: int(v) for k, v in top_categories},
        "by_merchant": {k: int(v) for k, v in top_merchants},
        "by_type": dict(by_type),
        "by_source": dict(by_source),
        "summary": "\n".join(lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reporte mensual de finanzas.")
    parser.add_argument("--month", required=True, help="Mes YYYY-MM, ej. 2026-05")
    parser.add_argument("--csv", default=DEFAULT_UNIFIED_CSV)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    csv_path = resolve_data_path(args.csv)
    if not csv_path.exists():
        print(json.dumps({"status": "error", "reason": "csv_not_found", "path": str(csv_path)}))
        raise SystemExit(1)

    links = load_movimiento_links(resolve_data_path(DEFAULT_MOVIMIENTO_LINKS))
    rows = [
        r
        for r in load_rows(csv_path, args.month)
        if not is_excluded_from_totals(r.get("movement_id") or "", links)
    ]
    result = summarize(rows, args.month)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["summary"])


if __name__ == "__main__":
    main()
