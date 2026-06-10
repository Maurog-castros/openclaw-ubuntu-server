"""Reporte por categoria desde finanzas_movimientos.csv."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import DEFAULT_UNIFIED_CSV, parse_clp, resolve_data_path
from finanzas_merchant_report import fmt_clp

CATEGORY_ALIASES = {
    "comida": {
        "bebidas",
        "carnes_pescados",
        "despensa",
        "embutidos",
        "frutas_verduras",
        "lacteos_huevos",
        "panaderia",
        "panaderia_fiambreria",
    },
    "alimentos": {
        "bebidas",
        "carnes_pescados",
        "despensa",
        "embutidos",
        "frutas_verduras",
        "lacteos_huevos",
        "panaderia",
        "panaderia_fiambreria",
    },
    "salud farmacia": {"salud_farmacia"},
    "farmacia": {"salud_farmacia"},
    "farmacias": {"salud_farmacia"},
    "simi": {"salud_farmacia"},
    "botilleria": {"botilleria"},
    "botillería": {"botilleria"},
    "oficina": {"oficina"},
    "electronica": {"electronica"},
    "electrónica": {"electronica"},
}


def load_rows(csv_path: Path) -> List[Dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def normalize_category_query(query: str) -> str:
    return " ".join((query or "").strip().lower().replace("_", " ").split())


def category_set(query: str) -> set[str]:
    normalized = normalize_category_query(query)
    if not normalized:
        return set()
    direct = (query or "").strip().lower()
    categories = set(CATEGORY_ALIASES.get(normalized, set()))
    if direct:
        categories.add(direct)
    categories.add(normalized.replace(" ", "_"))
    return categories


def include_row(row: Dict[str, str], categories: set[str]) -> bool:
    if not categories:
        return True
    return (row.get("category") or "").strip().lower() in categories


def filter_rows(
    rows: List[Dict[str, str]],
    *,
    month: str,
    date_from: str,
    date_to: str,
    category: str,
    source: str,
) -> List[Dict[str, str]]:
    categories = category_set(category)
    filtered: List[Dict[str, str]] = []
    for row in rows:
        if (row.get("movement_type") or "") not in {"gasto", "transferencia_salida"}:
            continue
        if source and (row.get("source") or "") != source:
            continue
        movement_date = (row.get("movement_date") or "")[:10]
        if month and not movement_date.startswith(month):
            continue
        if date_from and movement_date < date_from:
            continue
        if date_to and movement_date > date_to:
            continue
        if include_row(row, categories):
            filtered.append(row)
    return filtered


def summarize(rows: List[Dict[str, str]], period: str, *, category: str, detail: bool) -> Dict[str, Any]:
    total = 0
    by_category: dict[str, int] = defaultdict(int)
    by_merchant: dict[str, int] = defaultdict(int)
    movements: List[Dict[str, Any]] = []

    for row in rows:
        amount = int(parse_clp(row.get("amount_clp") or row.get("ticket_total")) or 0)
        if amount <= 0:
            continue
        total += amount
        cat = row.get("category") or "sin_categoria"
        merchant = row.get("merchant") or row.get("counterparty") or "desconocido"
        by_category[cat] += amount
        by_merchant[merchant] += amount
        movements.append(
            {
                "date": row.get("movement_date") or "",
                "merchant": merchant,
                "description": row.get("description") or "",
                "category": cat,
                "amount_clp": amount,
                "source": row.get("source") or "",
            }
        )

    categories_sorted = dict(sorted(by_category.items(), key=lambda item: item[1], reverse=True))
    merchants_sorted = dict(sorted(by_merchant.items(), key=lambda item: item[1], reverse=True)[:10])
    movements_sorted = sorted(movements, key=lambda item: (item["date"], item["amount_clp"]), reverse=True)

    title = f"Resumen categoria: {category}" if category else "Resumen por categoria"
    lines = [
        title,
        f"Periodo: {period}",
        f"Total: {fmt_clp(total)} en {len(movements)} movimientos",
        "",
        "Por categoria:",
    ]
    for name, amount in categories_sorted.items():
        lines.append(f"- {name}: {fmt_clp(amount)}")
    lines.extend(["", "Top comercios:"])
    for name, amount in merchants_sorted.items():
        lines.append(f"- {name}: {fmt_clp(amount)}")
    if detail:
        lines.extend(["", "Detalle:"])
        for item in movements_sorted[:40]:
            lines.append(
                f"- {item['date']}: {fmt_clp(item['amount_clp'])} "
                f"{item['merchant']} - {item['description'][:70]}"
            )

    return {
        "period": period,
        "category_query": category,
        "movement_count": len(movements),
        "total_clp": total,
        "by_category": categories_sorted,
        "by_merchant": merchants_sorted,
        "movements": movements_sorted if detail else movements_sorted[:15],
        "summary": "\n".join(lines),
        "whatsapp_reply": "\n".join(lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reporte por categoria.")
    parser.add_argument("--csv", default=DEFAULT_UNIFIED_CSV)
    parser.add_argument("--month", default="")
    parser.add_argument("--from", dest="date_from", default="")
    parser.add_argument("--to", dest="date_to", default=date.today().isoformat())
    parser.add_argument("--category", default="")
    parser.add_argument("--source", default="", help="Filtra source exacto, ej. santander_cartola.")
    parser.add_argument("--detail", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.month:
        period = args.month
    else:
        period = f"{args.date_from or 'inicio'}..{args.date_to or 'hoy'}"
    rows = filter_rows(
        load_rows(resolve_data_path(args.csv)),
        month=args.month,
        date_from=args.date_from,
        date_to=args.date_to,
        category=args.category,
        source=args.source,
    )
    result = summarize(rows, period, category=args.category, detail=args.detail)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["summary"])


if __name__ == "__main__":
    main()
