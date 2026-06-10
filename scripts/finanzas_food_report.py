"""Resumen de gasto en alimentos consumibles desde finanzas_movimientos.csv."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import DEFAULT_UNIFIED_CSV, parse_clp, resolve_data_path

FOOD_CATEGORIES = {
    "bebidas",
    "carnes_pescados",
    "despensa",
    "embutidos",
    "frutas_verduras",
    "lacteos_huevos",
    "panaderia",
    "panaderia_fiambreria",
}

FOOD_KEYWORDS = (
    "aceite",
    "agua",
    "arroz",
    "atun",
    "azucar",
    "bebida",
    "carne",
    "cebolla",
    "cerdo",
    "cereal",
    "chorizo",
    "churrasco",
    "chips",
    "despensa",
    "durazno",
    "embutido",
    "fideo",
    "fruta",
    "galleta",
    "hallulla",
    "huevo",
    "jamon",
    "jamón",
    "jugo",
    "leche",
    "lechuga",
    "mantequilla",
    "mango",
    "marraqueta",
    "papaya",
    "pizza",
    "mendosino",
    "mermelada",
    "palta",
    "pan",
    "pollo",
    "queso",
    "refresco",
    "salchicha",
    "salame",
    "salsa",
    "tomate",
    "verdura",
    "vinagre",
    "yogurt",
)

NON_FOOD_CATEGORIES = {
    "salud_farmacia",
    "limpieza_hogar",
    "cuidado_personal",
    "banco",
    "transferencias",
    "efectivo",
}


def fmt_clp(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")


def parse_iso_date(value: str) -> date | None:
    text = (value or "")[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def fmt_day(value: str) -> str:
    parsed = parse_iso_date(value)
    if not parsed:
        return value or "sin-fecha"
    return parsed.strftime("%d-%m-%y")


def row_is_food(row: dict[str, str]) -> bool:
    category = (row.get("category") or "").strip().lower()
    if category in NON_FOOD_CATEGORIES:
        return False
    if category in FOOD_CATEGORIES:
        return True
    text = " ".join(
        [
            row.get("description") or "",
            row.get("merchant") or "",
            row.get("merchant_branch") or "",
        ]
    ).lower()
    return any(keyword in text for keyword in FOOD_KEYWORDS)


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def filter_rows(
    rows: list[dict[str, str]],
    *,
    month: str = "",
    date_from: str = "",
    date_to: str = "",
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for row in rows:
        if (row.get("movement_type") or "") != "gasto":
            continue
        movement_date = row.get("movement_date") or ""
        if month and not movement_date.startswith(month):
            continue
        if date_from and movement_date < date_from:
            continue
        if date_to and movement_date > date_to:
            continue
        if row_is_food(row):
            result.append(row)
    return result


def summarize(rows: list[dict[str, str]], period: str, *, detail: bool) -> dict[str, Any]:
    total = 0
    by_category: dict[str, int] = defaultdict(int)
    by_merchant: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    movements: list[dict[str, Any]] = []

    for row in rows:
        amount = int(parse_clp(row.get("amount_clp") or row.get("ticket_total")) or 0)
        total += amount
        category = row.get("category") or "sin_categoria"
        merchant = row.get("merchant") or "desconocido"
        movement_date = row.get("movement_date") or ""
        by_category[category] += amount
        by_merchant[merchant] += amount
        by_day[movement_date] += amount
        movements.append(
            {
                "date": movement_date,
                "time": row.get("movement_time") or "",
                "merchant": merchant,
                "description": row.get("description") or "",
                "category": category,
                "amount_clp": amount,
                "source": row.get("source") or "",
                "document_number": row.get("document_number") or "",
            }
        )

    top_categories = dict(sorted(by_category.items(), key=lambda item: item[1], reverse=True))
    top_merchants = dict(sorted(by_merchant.items(), key=lambda item: item[1], reverse=True)[:10])
    sorted_movements = sorted(
        movements,
        key=lambda item: (item["date"], item["time"], item["amount_clp"]),
        reverse=True,
    )

    lines = [
        "Resumen alimentos consumibles",
        f"Periodo: {period}",
        f"Total: {fmt_clp(total)} en {len(rows)} movimientos",
        "",
        "Por categoria:",
    ]
    for category, amount in top_categories.items():
        lines.append(f"- {category}: {fmt_clp(amount)}")
    lines.extend(["", "Top comercios:"])
    for merchant, amount in top_merchants.items():
        lines.append(f"- {merchant}: {fmt_clp(amount)}")
    if detail and sorted_movements:
        lines.extend(["", "Detalle:"])
        for item in sorted_movements:
            when = fmt_day(item["date"])
            time = item["time"][:5] if item["time"] else ""
            prefix = f"- {when} {time}".strip()
            lines.append(
                f"{prefix}: {fmt_clp(item['amount_clp'])} - "
                f"{item['merchant']} - {item['description']}"
            )

    return {
        "period": period,
        "movement_count": len(rows),
        "total_clp": total,
        "by_category": top_categories,
        "by_merchant": top_merchants,
        "by_day": dict(sorted(by_day.items())),
        "movements": sorted_movements if detail else sorted_movements[:15],
        "summary": "\n".join(lines),
        "whatsapp_reply": "\n".join(lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Resumen de alimentos consumibles.")
    parser.add_argument("--month", default="", help="Mes YYYY-MM.")
    parser.add_argument("--from", dest="date_from", default="", help="Fecha desde YYYY-MM-DD.")
    parser.add_argument("--to", dest="date_to", default="", help="Fecha hasta YYYY-MM-DD.")
    parser.add_argument("--csv", default=DEFAULT_UNIFIED_CSV)
    parser.add_argument("--detail", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    csv_path = resolve_data_path(args.csv)
    rows = filter_rows(
        load_rows(csv_path),
        month=args.month,
        date_from=args.date_from,
        date_to=args.date_to,
    )
    period = args.month or (
        f"{args.date_from or 'inicio'}..{args.date_to or 'hoy'}"
        if args.date_from or args.date_to
        else "todo el historial"
    )
    result = summarize(rows, period, detail=args.detail)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["summary"])


if __name__ == "__main__":
    main()
