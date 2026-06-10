"""Listado compacto de transferencias de salida (evita volcar el CSV en el chat)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import (
    DEFAULT_OBSERVACIONES,
    DEFAULT_UNIFIED_CSV,
    DEFAULT_MOVIMIENTO_LINKS,
    load_movimiento_links,
    load_observaciones,
    is_excluded_from_totals,
    parse_clp,
    resolve_data_path,
)
from finanzas_merchant_report import (
    fmt_clp,
    fmt_date_dd_mm_yy,
    fmt_weekday,
    load_all_rows,
    parse_iso_date,
)

SALIDA_TYPES = frozenset({"transferencia_salida"})


def filter_salida_rows(
    rows: List[Dict[str, str]],
    *,
    days: int,
    date_from: str = "",
    date_to: str = "",
    limit: int = 0,
) -> List[Dict[str, str]]:
    today = date.today()
    if date_from:
        start = parse_iso_date(date_from)
    else:
        start = today - timedelta(days=max(days, 1) - 1)
    end = parse_iso_date(date_to) if date_to else today
    if not start:
        start = today - timedelta(days=14)

    out: List[Dict[str, str]] = []
    for row in rows:
        if (row.get("movement_type") or "") not in SALIDA_TYPES:
            continue
        movement_date = parse_iso_date(row.get("movement_date") or "")
        if not movement_date or movement_date < start or movement_date > end:
            continue
        out.append(row)

    out.sort(
        key=lambda r: (
            r.get("movement_date") or "",
            r.get("movement_time") or "",
            r.get("movement_datetime") or "",
        ),
        reverse=True,
    )
    if limit > 0:
        out = out[:limit]
    return out


def period_label(
    *,
    days: int,
    date_from: str,
    date_to: str,
    limit: int,
    days_explicit: bool,
) -> str:
    if limit > 0 and not days_explicit and not date_from:
        return f"últimas {limit} transferencias de salida"
    if limit > 0:
        base = f"últimos {days} días" if not date_from else f"{date_from} .. {date_to or 'hoy'}"
        return f"{base} (máx. {limit})"
    if date_from:
        return f"{date_from} .. {date_to or 'hoy'}"
    return f"últimos {days} días"


def build_line(row: Dict[str, str], observations: Dict[str, Dict[str, str]], links: Dict[str, Dict[str, str]]) -> str:
    amount = int(parse_clp(row.get("amount_clp") or row.get("ticket_total") or "0") or 0)
    iso = row.get("movement_date") or ""
    when = fmt_date_dd_mm_yy(iso)
    wd = fmt_weekday(iso)
    if wd:
        when = f"{when} ({wd})"
    desc = (row.get("description") or row.get("counterparty") or "").strip()
    source = row.get("source") or ""
    mid = row.get("movement_id") or ""
    if is_excluded_from_totals(mid, links):
        link = links.get(mid) or {}
        desc = f"↳ misma tx ({link.get('canonical_movement_id', '')[:8]}…) — {desc}"
    elif source and source != "santander_gmail":
        desc = f"{desc} [{source}]" if desc else f"[{source}]"
    line = f"{when} — {fmt_clp(amount)} — {desc}"
    note = (observations.get(mid, {}) or {}).get("note", "").strip()
    if note and not is_excluded_from_totals(mid, links):
        line += f" — Obs: {note}"
    return line


def build_summary(
    rows: List[Dict[str, str]],
    observations: Dict[str, Dict[str, str]],
    links: Dict[str, Dict[str, str]],
    *,
    days: int,
    date_from: str,
    date_to: str,
    limit: int,
    days_explicit: bool,
) -> str:
    counted = [r for r in rows if not is_excluded_from_totals(r.get("movement_id") or "", links)]
    total = sum(int(parse_clp(r.get("amount_clp") or "0") or 0) for r in counted)
    period = period_label(
        days=days,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        days_explicit=days_explicit,
    )
    lines = [
        f"=== Transferencias de salida ({period}) ===",
        f"Movimientos: {len(counted)}" + (f" (+{len(rows)-len(counted)} vinculados misma tx)" if len(rows) != len(counted) else ""),
        f"Total: {fmt_clp(total)}",
        "",
    ]
    if not rows:
        lines.append("Sin transferencias de salida en el periodo.")
        return "\n".join(lines)

    lines.append("Detalle (más reciente primero):")
    for row in rows:
        lines.append(f"• {build_line(row, observations, links)}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Transferencias de salida desde CSV unificado.")
    parser.add_argument("--csv", default=DEFAULT_UNIFIED_CSV)
    parser.add_argument("--days", type=int, default=15, help="Ventana hacia atrás desde hoy (default 15).")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Máximo de filas (ej. 10 = las 10 más recientes). Sin --days explícito busca hasta 365 días.",
    )
    parser.add_argument("--from", dest="date_from", default="", help="YYYY-MM-DD inicio (opcional).")
    parser.add_argument("--to", dest="date_to", default="", help="YYYY-MM-DD fin (opcional).")
    parser.add_argument("--observaciones", default=DEFAULT_OBSERVACIONES)
    parser.add_argument("--links", default=DEFAULT_MOVIMIENTO_LINKS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    days_explicit = "--days" in sys.argv
    scan_days = args.days
    if args.limit > 0 and not days_explicit and not args.date_from:
        scan_days = 365

    csv_path = resolve_data_path(args.csv)
    observations = load_observaciones(resolve_data_path(args.observaciones))
    links = load_movimiento_links(resolve_data_path(args.links))
    rows = filter_salida_rows(
        load_all_rows(csv_path),
        days=scan_days,
        date_from=args.date_from,
        date_to=args.date_to,
        limit=args.limit,
    )
    total = sum(
        int(parse_clp(r.get("amount_clp") or "0") or 0)
        for r in rows
        if not is_excluded_from_totals(r.get("movement_id") or "", links)
    )
    payload = {
        "days": scan_days,
        "limit": args.limit,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "movement_count": len(rows),
        "total_clp": total,
        "summary": build_summary(
            rows,
            observations,
            links,
            days=scan_days,
            date_from=args.date_from,
            date_to=args.date_to,
            limit=args.limit,
            days_explicit=days_explicit,
        ),
        "items": [
            {
                "movement_id": r.get("movement_id") or "",
                "date": r.get("movement_date"),
                "amount_clp": int(parse_clp(r.get("amount_clp") or "0") or 0),
                "description": r.get("description") or "",
                "counterparty": r.get("counterparty") or "",
                "source": r.get("source") or "",
                "observation": (observations.get(r.get("movement_id") or "", {}) or {}).get("note", ""),
            }
            for r in rows
        ],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["summary"])


if __name__ == "__main__":
    main()
