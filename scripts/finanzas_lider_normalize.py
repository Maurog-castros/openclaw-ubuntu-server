"""Normaliza filas Lider con columnas historicas corridas."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

CSV_COLUMNS = [
    "processed_at",
    "purchase_date",
    "purchase_time",
    "purchase_datetime",
    "store",
    "store_branch",
    "receipt_number",
    "message_id",
    "attachment_name",
    "product",
    "category",
    "line_amount",
    "ticket_total",
]


def is_amount(value: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", (value or "").strip()))


def is_time(value: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", (value or "").strip()))


def is_shifted(row: Dict[str, str]) -> bool:
    return (
        is_time(row.get("store", ""))
        and is_amount(row.get("store_branch", ""))
        and row.get("ticket_total", "").lower().endswith(".pdf")
    )


def repair_shifted(row: Dict[str, str]) -> Dict[str, str]:
    return {
        "processed_at": row.get("processed_at", ""),
        "purchase_date": row.get("purchase_date", ""),
        "purchase_time": row.get("store", ""),
        "purchase_datetime": row.get("message_id", ""),
        "store": row.get("attachment_name", "") or "lider",
        "store_branch": row.get("product", ""),
        "receipt_number": row.get("category", ""),
        "message_id": row.get("line_amount", ""),
        "attachment_name": row.get("ticket_total", ""),
        "product": row.get("purchase_time", ""),
        "category": row.get("purchase_datetime", ""),
        "line_amount": row.get("store_branch", ""),
        "ticket_total": row.get("receipt_number", ""),
    }


def normalize(csv_file: Path) -> Dict[str, int | str]:
    if not csv_file.exists():
        return {"status": "missing", "rows": 0, "fixed": 0}

    with csv_file.open(newline="", encoding="utf-8") as handle:
        rows: List[Dict[str, str]] = list(csv.DictReader(handle))

    fixed = 0
    normalized: List[Dict[str, str]] = []
    for row in rows:
        clean = {col: row.get(col, "") for col in CSV_COLUMNS}
        if is_shifted(clean):
            clean = repair_shifted(clean)
            fixed += 1
        normalized.append(clean)

    if fixed:
        backup = csv_file.with_name(
            f"{csv_file.name}.bak-normalize-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        backup.write_text(csv_file.read_text(encoding="utf-8"), encoding="utf-8")
        with csv_file.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(normalized)
        backup_name = str(backup)
    else:
        backup_name = ""

    return {
        "status": "ok",
        "rows": len(rows),
        "fixed": fixed,
        "backup": backup_name,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Normaliza data/lider_receipts.csv.")
    parser.add_argument("--csv", default="data/lider_receipts.csv")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = normalize(Path(args.csv))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Filas: {result['rows']} | corregidas: {result['fixed']}")


if __name__ == "__main__":
    main()
