#!/usr/bin/env python3
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "data" / "lider_receipts.csv"

if not CSV_PATH.exists():
    raise SystemExit(f"No existe CSV: {CSV_PATH}")

def money(value: str) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0

def parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None

rows: list[dict[str, str]] = []
with CSV_PATH.open(newline="", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))

if not rows:
    raise SystemExit("CSV Lider sin filas")

seen_tickets: set[tuple[str, str, str]] = set()
total_spent = 0.0
categories: dict[str, list[float]] = defaultdict(list)
products: dict[str, list[float]] = defaultdict(list)
dates: list[datetime] = []

for row in rows:
    amount = money(row.get("line_amount", "0"))
    total = money(row.get("ticket_total", "0"))
    ticket_key = (
        row.get("message_id", ""),
        row.get("receipt_number", ""),
        row.get("ticket_total", ""),
    )
    if ticket_key not in seen_tickets:
        seen_tickets.add(ticket_key)
        total_spent += total

    categories[row.get("category") or "sin_categoria"].append(amount)
    products[row.get("product") or "sin_producto"].append(amount)
    parsed = parse_date(row.get("purchase_date", ""))
    if parsed:
        dates.append(parsed)

num_tickets = len(seen_tickets)
avg_ticket = total_spent / num_tickets if num_tickets else 0.0
min_date = min(dates).strftime("%Y-%m-%d") if dates else "sin fecha"
max_date = max(dates).strftime("%Y-%m-%d") if dates else "sin fecha"

cat_summary = sorted(
    ((name, sum(values), len(values)) for name, values in categories.items()),
    key=lambda item: item[1],
    reverse=True,
)
prod_summary = sorted(
    ((name, sum(values), len(values)) for name, values in products.items()),
    key=lambda item: item[1],
    reverse=True,
)[:10]

print("=== RESUMEN EJECUTIVO GASTOS LIDER ===")
print(f"Periodo: {min_date} al {max_date}")
print(f"Total gastado: ${total_spent:,.0f}")
print(f"Boletas: {num_tickets}")
print(f"Promedio boleta: ${avg_ticket:,.0f}")
print()
print("--- GASTO POR CATEGORIA ---")
for cat, total, count in cat_summary:
    print(f"{cat}: ${total:,.0f} ({count} items)")
print()
print("--- TOP 10 PRODUCTOS (por monto) ---")
for prod, total, count in prod_summary:
    print(f"{prod[:45]}: ${total:,.0f} x{count}")
