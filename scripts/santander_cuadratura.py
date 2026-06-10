"""Cuadratura: movimientos cartola Santander vs CSV unificado de finanzas."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import DEFAULT_CARTOLA_CSV, DEFAULT_UNIFIED_CSV, parse_clp


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def month_range(month: str) -> Tuple[str, str]:
    year_s, month_s = month.split("-")
    year, month_i = int(year_s), int(month_s)
    start = f"{year:04d}-{month_i:02d}-01"
    if month_i == 12:
        end = f"{year + 1:04d}-01-01"
    else:
        end = f"{year:04d}-{month_i + 1:02d}-01"
    return start, end


def in_range(date: str, start: str, end: str) -> bool:
    if not date:
        return False
    return start <= date < end


def normalize_desc(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def merchant_hint(description: str) -> str:
    lowered = normalize_desc(description)
    if "lider" in lowered or "hyper" in lowered or "hiper" in lowered:
        return "lider"
    if "transf" in lowered:
        return "transferencia"
    if "compra" in lowered:
        return "compra_tarjeta"
    return "otro"


def cartola_entries(rows: List[Dict[str, str]], start: str, end: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for row in rows:
        date = row.get("movement_date") or ""
        if not in_range(date, start, end):
            continue
        charge = parse_clp(row.get("charge_clp")) or 0
        credit = parse_clp(row.get("credit_clp")) or 0
        amount = charge or credit
        if amount <= 0:
            continue
        entries.append(
            {
                "date": date,
                "amount": amount,
                "direction": "cargo" if charge else "abono",
                "description": row.get("description") or "",
                "document_number": row.get("document_number") or "",
                "branch": row.get("branch") or "",
                "hint": merchant_hint(row.get("description") or ""),
                "source_row": row,
            }
        )
    return entries


def finanzas_entries(rows: List[Dict[str, str]], start: str, end: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for row in rows:
        date = row.get("movement_date") or ""
        if not in_range(date, start, end):
            continue
        amount = parse_clp(row.get("amount_clp") or row.get("ticket_total")) or 0
        if amount <= 0:
            continue
        entries.append(
            {
                "date": date,
                "amount": amount,
                "description": row.get("description") or row.get("merchant") or "",
                "merchant": row.get("merchant") or "",
                "source": row.get("source") or "",
                "movement_type": row.get("movement_type") or "",
                "source_row": row,
            }
        )
    return entries


def match_entries(
    cartola: List[Dict[str, Any]],
    finanzas: List[Dict[str, Any]],
    period_start: str,
    period_end: str,
) -> Dict[str, Any]:
    fin_by_key: Dict[Tuple[str, int], List[int]] = defaultdict(list)
    for idx, item in enumerate(finanzas):
        fin_by_key[(item["date"], item["amount"])].append(idx)

    matched: List[Dict[str, Any]] = []
    solo_cartola: List[Dict[str, Any]] = []
    used_fin: set[int] = set()

    for c_item in cartola:
        key = (c_item["date"], c_item["amount"])
        candidates = [i for i in fin_by_key.get(key, []) if i not in used_fin]
        if candidates:
            fin_idx = candidates[0]
            used_fin.add(fin_idx)
            f_item = finanzas[fin_idx]
            matched.append(
                {
                    "date": c_item["date"],
                    "amount": c_item["amount"],
                    "cartola_desc": c_item["description"],
                    "finanzas_desc": f_item["description"],
                    "finanzas_source": f_item["source"],
                    "finanzas_merchant": f_item["merchant"],
                }
            )
        else:
            solo_cartola.append(c_item)

    solo_finanzas = [finanzas[i] for i in range(len(finanzas)) if i not in used_fin]

    total_cargos_cartola = sum(x["amount"] for x in cartola if x["direction"] == "cargo")
    total_cargos_fin = sum(
        x["amount"]
        for x in finanzas
        if x["movement_type"] in ("gasto", "transferencia_salida") or x["source"] != "santander_gmail"
    )

    lines = [
        f"=== Cuadratura Santander {period_start} .. {period_end} ===",
        f"Movimientos cartola: {len(cartola)}",
        f"Movimientos finanzas: {len(finanzas)}",
        f"Conciliados (misma fecha+monto): {len(matched)}",
        f"Solo en cartola: {len(solo_cartola)}",
        f"Solo en finanzas: {len(solo_finanzas)}",
        f"Total cargos cartola: ${total_cargos_cartola:,} CLP".replace(",", "."),
    ]

    if solo_cartola:
        lines.append("")
        lines.append("Solo cartola (muestra):")
        for item in solo_cartola[:15]:
            lines.append(f"- {item['date']} ${item['amount']:,} {item['description'][:60]}".replace(",", "."))

    if solo_finanzas:
        lines.append("")
        lines.append("Solo finanzas (muestra):")
        for item in solo_finanzas[:15]:
            lines.append(
                f"- {item['date']} ${item['amount']:,} [{item['source']}] {item['description'][:50]}".replace(",", ".")
            )

    return {
        "period_start": period_start,
        "period_end": period_end,
        "cartola_count": len(cartola),
        "finanzas_count": len(finanzas),
        "matched_count": len(matched),
        "solo_cartola_count": len(solo_cartola),
        "solo_finanzas_count": len(solo_finanzas),
        "matched": matched,
        "solo_cartola": solo_cartola,
        "solo_finanzas": solo_finanzas,
        "summary": "\n".join(lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Cuadratura cartola Santander vs finanzas.")
    parser.add_argument("--month", required=True, help="Mes YYYY-MM del periodo a cuadrar")
    parser.add_argument("--cartola-csv", default=DEFAULT_CARTOLA_CSV)
    parser.add_argument("--unified-csv", default=DEFAULT_UNIFIED_CSV)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    start, end = month_range(args.month)

    cartola_rows = read_csv(Path(args.cartola_csv))
    unified_rows = read_csv(Path(args.unified_csv))

    c_entries = cartola_entries(cartola_rows, start, end)
    f_entries = finanzas_entries(unified_rows, start, end)
    result = match_entries(c_entries, f_entries, start, end)

    if args.json:
        slim = {k: v for k, v in result.items() if k not in {"matched", "solo_cartola", "solo_finanzas"}}
        slim["matched_sample"] = result["matched"][:20]
        slim["solo_cartola_sample"] = [
            {"date": x["date"], "amount": x["amount"], "description": x["description"]}
            for x in result["solo_cartola"][:20]
        ]
        slim["solo_finanzas_sample"] = [
            {
                "date": x["date"],
                "amount": x["amount"],
                "source": x["source"],
                "description": x["description"],
            }
            for x in result["solo_finanzas"][:20]
        ]
        print(json.dumps(slim, ensure_ascii=False, indent=2))
    else:
        print(result["summary"])


if __name__ == "__main__":
    main()
