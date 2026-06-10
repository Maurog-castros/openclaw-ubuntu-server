"""Reporte apoyo familiar CASTRO DIAZ GUILLERMO."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


def parse_clp(value: str) -> int:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    return int(digits) if digits else 0


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", (value or "").upper())).strip()


def read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def summarize(path: Path, from_date: str, name: str) -> Dict[str, Any]:
    needle = norm(name)
    fallback_needles = [needle, "CASTRO DIAZ"]
    matches: List[Dict[str, Any]] = []
    total = 0
    by_month: Counter[str] = Counter()

    for row in read_rows(path):
        movement_date = (row.get("movement_date") or "")[:10]
        if movement_date < from_date:
            continue
        hay = norm(" ".join([row.get("description") or "", row.get("counterparty") or "", row.get("category") or ""]))
        if not any(item and item in hay for item in fallback_needles) and "APOYO FAMILIAR" not in hay:
            continue
        amount = parse_clp(row.get("amount_clp") or row.get("ticket_total"))
        if amount <= 0:
            continue
        movement_type = (row.get("movement_type") or "").lower()
        signed = amount if movement_type in {"transferencia_entrada", "ingreso"} else -amount
        total += signed
        by_month[movement_date[:7]] += signed
        matches.append(
            {
                "date": movement_date,
                "amount_clp": signed,
                "source": row.get("source") or "",
                "description": row.get("description") or row.get("counterparty") or "",
                "movement_id": row.get("movement_id") or "",
            }
        )

    matches.sort(key=lambda item: (item["date"], item["movement_id"]), reverse=True)
    lines = [
        f"Apoyo familiar {name} desde {from_date}:",
        f"Total: ${total:,}".replace(",", "."),
        f"Movimientos: {len(matches)}",
    ]
    if by_month:
        monthly = ", ".join(f"{m}: ${v:,}".replace(",", ".") for m, v in sorted(by_month.items()))
        lines.append(f"Por mes: {monthly}")
    if matches:
        latest = matches[0]
        lines.append(f"Ultimo: {latest['date']} {'+' if latest['amount_clp'] >= 0 else '-'}${abs(latest['amount_clp']):,}".replace(",", "."))

    return {
        "status": "ok",
        "from_date": from_date,
        "name": name,
        "total_clp": total,
        "count": len(matches),
        "by_month": dict(sorted(by_month.items())),
        "latest": matches[:10],
        "summary": "\n".join(lines),
        "whatsapp_reply": "\n".join(lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Suma apoyo familiar por contraparte.")
    parser.add_argument("--csv", default="data/finanzas_movimientos.csv")
    parser.add_argument("--from-date", default="2026-01-01")
    parser.add_argument("--name", default="CASTRO DIAZ GUILLERMO")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = summarize(Path(args.csv), args.from_date, args.name)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["summary"])


if __name__ == "__main__":
    main()
