"""Gasto por alias de comercio (ej. mall chino -> Comercial Kaisheng)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import (
    DEFAULT_MERCHANT_ALIASES,
    DEFAULT_UNIFIED_CSV,
    alias_patterns,
    find_alias_by_query,
    load_merchant_aliases,
    parse_clp,
    resolve_data_path,
    row_matches_alias,
)

WEEKDAY_ES = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)


def parse_iso_date(value: str) -> Optional[date]:
    text = (value or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def fmt_date_dd_mm_yy(iso_date: str) -> str:
    parsed = parse_iso_date(iso_date)
    if not parsed:
        return iso_date or ""
    return parsed.strftime("%d-%m-%y")


def fmt_weekday(iso_date: str) -> str:
    parsed = parse_iso_date(iso_date)
    if not parsed:
        return ""
    return WEEKDAY_ES[parsed.weekday()].capitalize()


def fmt_time_24h(time_str: str) -> str:
    text = (time_str or "").strip()
    if not text:
        return ""
    for pattern in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, pattern).strftime("%H:%M")
        except ValueError:
            continue
    if len(text) >= 5 and text[2] == ":":
        return text[:5]
    return text


def fmt_clp(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")


def load_all_rows(csv_path: Path) -> List[Dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def filter_rows(
    rows: List[Dict[str, str]],
    *,
    month: str = "",
    date_from: str = "",
    date_to: str = "",
) -> List[Dict[str, str]]:
    filtered: List[Dict[str, str]] = []
    for row in rows:
        date = row.get("movement_date") or ""
        if month and not date.startswith(month):
            continue
        if date_from and date < date_from:
            continue
        if date_to and date > date_to:
            continue
        filtered.append(row)
    return filtered


def movement_detail_from_row(row: Dict[str, str]) -> Dict[str, Any]:
    date = (row.get("movement_date") or "").strip()
    time = (row.get("movement_time") or "").strip()
    dt = (row.get("movement_datetime") or "").strip()
    if not time and dt:
        if "T" in dt:
            parts = dt.split("T", 1)
            if not date:
                date = parts[0]
            time = parts[1][:8] if len(parts) > 1 else ""
        elif len(dt) > 10 and dt[10:11] in (" ", "T"):
            if not date:
                date = dt[:10]
            time = dt[11:19].strip()

    source = row.get("source") or ""
    time_known = bool(time and time not in ("00:00:00", "00:00"))
    if source in ("santander_cartola", "santander_gmail") and not time_known:
        time = ""
        time_known = False

    amount = parse_clp(row.get("amount_clp") or row.get("ticket_total")) or 0
    date_display = fmt_date_dd_mm_yy(date)
    weekday = fmt_weekday(date)
    time_display = fmt_time_24h(time) if time_known else ""
    when_display = f"{date_display} ({weekday})" if weekday else date_display
    if time_display:
        when_display = f"{when_display} {time_display}"

    return {
        "date": date,
        "date_display": date_display,
        "weekday": weekday,
        "time": time,
        "time_display": time_display,
        "time_known": time_known,
        "when_display": when_display,
        "datetime_display": when_display,
        "amount_clp": amount,
        "description": row.get("description") or row.get("merchant") or "",
        "merchant": row.get("merchant") or "",
        "merchant_branch": row.get("merchant_branch") or "",
        "source": source,
        "source_label": _source_label(source),
        "category": row.get("category") or "",
        "payment_method": row.get("payment_method") or "",
        "document_number": row.get("document_number") or "",
    }


def _source_label(source: str) -> str:
    labels = {
        "santander_cartola": "Cartola Santander",
        "santander_gmail": "Transferencia Santander",
        "lider_gmail": "Boleta Lider (Gmail)",
        "telegram_foto": "Foto boleta",
        "whatsapp_foto": "Foto boleta (WhatsApp)",
        "openclaw_web": "Boleta web",
        "manual": "Manual",
    }
    return labels.get(source, source or "desconocido")


def group_movements_by_day(movements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_day: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in movements:
        day = item.get("date") or "sin-fecha"
        by_day[day].append(item)
    days: List[Dict[str, Any]] = []
    for day in sorted(by_day):
        items = sorted(by_day[day], key=lambda x: (x.get("time") or "", x.get("amount_clp", 0)))
        subtotal = sum(int(x.get("amount_clp") or 0) for x in items)
        days.append(
            {
                "date": day,
                "date_display": fmt_date_dd_mm_yy(day),
                "weekday": fmt_weekday(day),
                "movement_count": len(items),
                "subtotal_clp": subtotal,
                "movements": items,
            }
        )
    return days


def movement_detail_label(item: Dict[str, Any]) -> str:
    desc = (item.get("description") or "")[:55]
    pay = item.get("payment_method") or ""
    if pay:
        return f"{desc} ({pay})"
    return desc


def build_detail_mobile(
    movements: List[Dict[str, Any]],
    *,
    show_time: bool,
) -> str:
    """Listado vertical para WhatsApp/Telegram (sin tablas markdown)."""
    if not movements:
        return ""
    lines: List[str] = []
    for block in group_movements_by_day(movements):
        date_display = block.get("date_display") or fmt_date_dd_mm_yy(block.get("date") or "")
        weekday = block.get("weekday") or fmt_weekday(block.get("date") or "")
        count = block["movement_count"]
        subtotal = int(block["subtotal_clp"])
        day_label = f"{date_display} ({weekday})" if weekday else date_display

        if count == 1:
            item = block["movements"][0]
            header = _movement_header_line(item, show_time=show_time)
            lines.append(header)
            lines.append(f"  {movement_detail_label(item)}")
            lines.append("")
            continue

        lines.append(f"{day_label} · {count} compras · {fmt_clp(subtotal)}")
        for item in block["movements"]:
            amount = fmt_clp(int(item.get("amount_clp") or 0))
            time_part = ""
            if show_time and item.get("time_display"):
                time_part = f"{item['time_display']} · "
            desc = movement_detail_label(item)
            lines.append(f"  · {time_part}{amount} — {desc}")
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _movement_header_line(item: Dict[str, Any], *, show_time: bool) -> str:
    date_display = item.get("date_display") or fmt_date_dd_mm_yy(item.get("date") or "")
    weekday = item.get("weekday") or fmt_weekday(item.get("date") or "")
    amount = fmt_clp(int(item.get("amount_clp") or 0))
    day_part = f"{date_display} ({weekday})" if weekday else date_display
    if show_time and item.get("time_display"):
        return f"· {day_part} {item['time_display']} · {amount}"
    return f"· {day_part} · {amount}"


def build_detail_table(
    movements: List[Dict[str, Any]],
    *,
    show_time: bool,
) -> str:
    if not movements:
        return ""
    headers = ["Fecha", "Día"]
    if show_time:
        headers.append("Hora")
    headers.extend(["Monto", "Detalle"])
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for item in movements:
        cols = [
            item.get("date_display") or fmt_date_dd_mm_yy(item.get("date") or ""),
            item.get("weekday") or fmt_weekday(item.get("date") or ""),
        ]
        if show_time:
            cols.append(item.get("time_display") or "")
        cols.append(fmt_clp(int(item.get("amount_clp") or 0)))
        cols.append(movement_detail_label(item))
        lines.append("| " + " | ".join(cols) + " |")
    return "\n".join(lines)


def build_detail_summary(
    label: str,
    period: str,
    movements: List[Dict[str, Any]],
    *,
    time_available_count: int,
) -> str:
    total = sum(int(m.get("amount_clp") or 0) for m in movements)
    show_time = time_available_count > 0
    sorted_rows = sorted(
        movements,
        key=lambda x: (x.get("date") or "", x.get("time") or "", x.get("amount_clp", 0)),
    )

    lines = [
        f"Detalle: {label}",
        f"Periodo: {period}",
        f"Total: {fmt_clp(total)} en {len(movements)} movimientos",
        "",
        build_detail_mobile(sorted_rows, show_time=show_time),
    ]
    if movements and not show_time:
        lines.extend(
            [
                "",
                "Nota: la cartola Santander no incluye hora (solo fecha dd-mm-yy). "
                "Boletas por foto pueden incluir hora en formato 24h.",
            ]
        )
    elif show_time and time_available_count < len(movements):
        lines.extend(
            [
                "",
                f"Nota: hora disponible solo en {time_available_count} de {len(movements)} movimientos.",
            ]
        )
    return "\n".join(lines)


def summarize_alias(
    alias: Dict[str, Any],
    matched: List[Dict[str, str]],
    *,
    month: str = "",
    date_from: str = "",
    date_to: str = "",
    detail: bool = False,
) -> Dict[str, Any]:
    total = 0
    by_month: Dict[str, int] = defaultdict(int)
    movements: List[Dict[str, Any]] = []
    time_available_count = 0

    for row in matched:
        item = movement_detail_from_row(row)
        amount = int(item["amount_clp"])
        total += amount
        date = item["date"]
        if date:
            by_month[date[:7]] += amount
        if item.get("time_known"):
            time_available_count += 1
        movements.append(item)

    label = alias.get("label") or alias.get("id") or "alias"
    period = month or (f"{date_from}..{date_to}" if date_from or date_to else "todo el historial")
    patterns = alias.get("patterns") or alias_patterns(alias)

    lines = [
        f"=== Gasto: {label} ===",
        f"Periodo: {period}",
        f"Movimientos: {len(matched)}",
        f"Total: {fmt_clp(total)}",
        f"Patrones: {', '.join(patterns)}",
    ]
    if by_month:
        lines.append("")
        lines.append("Por mes:")
        for key in sorted(by_month):
            lines.append(f"- {key}: {fmt_clp(by_month[key])}")

    if movements and not detail:
        lines.append("")
        lines.append("Detalle (ultimos 15):")
        for item in sorted(movements, key=lambda x: x["date"], reverse=True)[:15]:
            desc = (item["description"] or "")[:55]
            when = item.get("when_display") or item.get("date_display") or ""
            lines.append(f"- {when} {fmt_clp(int(item['amount_clp']))} {desc}")

    sorted_movements = sorted(
        movements,
        key=lambda x: (x.get("date") or "", x.get("time") or "", x.get("amount_clp", 0)),
    )
    detail_limit = len(sorted_movements) if detail else 20

    result: Dict[str, Any] = {
        "alias_id": alias.get("id"),
        "alias_label": label,
        "period": period,
        "movement_count": len(matched),
        "total_clp": total,
        "by_month": dict(sorted(by_month.items())),
        "by_day": group_movements_by_day(sorted_movements),
        "patterns": list(patterns),
        "notes": alias.get("notes") or "",
        "time_available_count": time_available_count,
        "time_available": time_available_count > 0,
        "data_quality_note": (
            ""
            if time_available_count
            else "Cartola Santander: solo fecha (sin hora). Boletas por foto pueden incluir hora."
        ),
        "movements": sorted_movements if detail else [],
        "movements_sample": sorted_movements[:detail_limit],
        "summary": "\n".join(lines),
    }
    if detail:
        show_time = time_available_count > 0
        result["detail_mobile"] = build_detail_mobile(sorted_movements, show_time=show_time)
        result["detail_table_markdown"] = build_detail_table(sorted_movements, show_time=show_time)
        result["detail_summary"] = build_detail_summary(
            label,
            period,
            sorted_movements,
            time_available_count=time_available_count,
        )
        result["summary"] = result["detail_summary"]
    return result


def list_aliases(aliases: List[Dict[str, Any]]) -> str:
    lines = ["Alias configurados:"]
    for alias in aliases:
        label = alias.get("label") or alias.get("id")
        patterns = ", ".join(alias.get("patterns") or [])
        note = alias.get("notes") or ""
        lines.append(f"- {label}: [{patterns}] {note}".strip())
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gasto por alias de comercio.")
    parser.add_argument("--alias", help='Nombre alias, ej. "mall chino" o id mall-chino')
    parser.add_argument("--month", default="", help="Filtrar YYYY-MM")
    parser.add_argument("--year", default="", help="Filtrar YYYY (ej. 2026)")
    parser.add_argument("--from", dest="date_from", default="", help="Fecha desde YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", default="", help="Fecha hasta YYYY-MM-DD")
    parser.add_argument("--csv", default=DEFAULT_UNIFIED_CSV)
    parser.add_argument("--aliases-file", default=DEFAULT_MERCHANT_ALIASES)
    parser.add_argument("--list", action="store_true", help="Lista alias disponibles")
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Listado completo agrupado por dia (hora si existe en boletas)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.year and not args.month:
        args.date_from = args.date_from or f"{args.year}-01-01"
        args.date_to = args.date_to or f"{args.year}-12-31"

    aliases = load_merchant_aliases(resolve_data_path(args.aliases_file))
    if args.list:
        output = {"aliases": aliases, "summary": list_aliases(aliases)}
        print(json.dumps(output, ensure_ascii=False, indent=2) if args.json else output["summary"])
        return

    if not args.alias:
        print(json.dumps({"status": "error", "reason": "missing_alias"}, ensure_ascii=False))
        raise SystemExit(1)

    alias = find_alias_by_query(aliases, args.alias)
    if not alias:
        known = ", ".join(str(a.get("label") or a.get("id")) for a in aliases)
        print(
            json.dumps(
                {
                    "status": "error",
                    "reason": "alias_not_found",
                    "query": args.alias,
                    "known_aliases": known,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1)

    rows = filter_rows(
        load_all_rows(resolve_data_path(args.csv)),
        month=args.month,
        date_from=args.date_from,
        date_to=args.date_to,
    )
    matched = [row for row in rows if row_matches_alias(row, alias)]
    result = summarize_alias(
        alias,
        matched,
        month=args.month,
        date_from=args.date_from,
        date_to=args.date_to,
        detail=args.detail,
    )
    result["status"] = "ok"

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["summary"])


if __name__ == "__main__":
    main()
