"""Vincula la misma transaccion registrada por varias fuentes (Gmail + screenshot app)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import (
    DEFAULT_MOVIMIENTO_LINKS,
    DEFAULT_UNIFIED_CSV,
    TRANSFER_SOURCE_LABELS,
    find_movements,
    is_excluded_from_totals,
    link_label,
    load_movimiento_links,
    movement_label,
    movement_row_text,
    normalize_store_name,
    parse_clp,
    parse_flexible_date,
    pick_canonical_transfer,
    resolve_data_path,
    save_movimiento_links,
)
from finanzas_saldo import parse_balance_text
from finanzas_merchant_report import fmt_clp, fmt_date_dd_mm_yy, load_all_rows, parse_iso_date

DEDUPE_HINT_RE = re.compile(
    r"\b(duplicad|mismo\s+monto|otra\s+vez|corrige|es\s+la\s+misma|misma\s+transacc)\b",
    re.I,
)
AMOUNT_IN_TEXT_RE = re.compile(r"\$\s*(\d{1,3}(?:\.\d{3})+|\d{4,})")


def parse_amount_from_text(text: str) -> Optional[int]:
    m = AMOUNT_IN_TEXT_RE.search(text or "")
    if m:
        return parse_clp(m.group(1))
    return parse_balance_text(text or "")


def parse_match_from_text(text: str) -> str:
    t = text or ""
    m = re.search(r"TRANSF\s+A\s+([A-Z0-9\s]+)", t, re.I)
    if m:
        return m.group(1).strip()[:40]
    m = re.search(r"\b([A-Z]{4,}(?:\s+[A-Z]{3,}){0,4})\b", t)
    if m:
        return m.group(1).strip()[:40]
    return ""


def find_duplicate_group(
    rows: List[Dict[str, str]],
    *,
    amount_clp: int,
    match: str = "",
    ref: str = "",
    date_hint: str = "",
    window_days: int = 10,
) -> List[Dict[str, str]]:
    needle = normalize_store_name(match)
    ref_digits = re.sub(r"\D", "", ref or "")
    center = parse_iso_date(parse_flexible_date(date_hint)) if date_hint else None
    if center is None:
        candidates = find_movements(rows, amount_clp=amount_clp, counterparty_contains=match or "")
        if candidates:
            center = parse_iso_date(candidates[0].get("movement_date") or "")
    if center is None:
        center = date.today()

    start = center - timedelta(days=window_days)
    end = center + timedelta(days=window_days)
    group: List[Dict[str, str]] = []

    for row in rows:
        amt = int(parse_clp(row.get("amount_clp") or row.get("ticket_total") or "0") or 0)
        if amt != int(amount_clp):
            continue
        md = parse_iso_date(row.get("movement_date") or "")
        if md and (md < start or md > end):
            continue
        hay = normalize_store_name(movement_row_text(row))
        if needle and needle not in hay:
            continue
        doc = re.sub(r"\D", "", row.get("document_number") or "")
        if ref_digits and doc and ref_digits not in doc and doc not in ref_digits:
            if needle not in hay:
                continue
        group.append(row)
    return group


def cmd_auto_link(args: argparse.Namespace) -> Dict[str, Any]:
    csv_path = resolve_data_path(args.csv)
    links_path = resolve_data_path(args.links)
    rows = load_all_rows(csv_path)
    links = load_movimiento_links(links_path)

    amount = args.amount
    if amount is None and args.text:
        amount = parse_amount_from_text(args.text)
    if amount is None:
        return {"status": "error", "message": "Indica --amount o texto con monto ($381.723)."}

    match = (args.match or "").strip() or parse_match_from_text(args.text or "")
    if not match:
        return {"status": "error", "message": "Indica --match (ej. RENOVAL) o nombre en el texto."}

    group = find_duplicate_group(
        rows,
        amount_clp=int(amount),
        match=match,
        ref=args.ref or "",
        date_hint=args.date or "",
        window_days=args.window_days,
    )
    if len(group) < 2:
        return {
            "status": "not_found",
            "message": f"No hay grupo duplicado para {fmt_clp(int(amount))} / {match} (encontrados: {len(group)}).",
            "candidates": [
                {
                    "movement_id": r.get("movement_id"),
                    "date": r.get("movement_date"),
                    "source": r.get("source"),
                    "description": movement_label(r),
                }
                for r in find_movements(rows, amount_clp=int(amount), counterparty_contains=match)[:10]
            ],
        }

    canonical = pick_canonical_transfer(group)
    canon_id = canonical.get("movement_id") or ""
    linked: List[Dict[str, str]] = []

    for row in group:
        mid = row.get("movement_id") or ""
        if not mid or mid == canon_id:
            continue
        src = row.get("source") or ""
        note = (
            f"Misma transaccion que {canon_id[:8]}… ({link_label(canonical)}). "
            f"No contar aparte — fuente {TRANSFER_SOURCE_LABELS.get(src, src)}."
        )
        links[mid] = {
            "canonical_movement_id": canon_id,
            "exclude_from_totals": True,
            "reason": "misma_transaccion_multi_fuente",
            "note": note,
            "source": src,
            "amount_clp": str(int(parse_clp(row.get("amount_clp") or "0") or 0)),
            "movement_date": row.get("movement_date") or "",
            "updated_at": date.today().isoformat(),
        }
        linked.append(row)

    save_movimiento_links(links_path, links)

    lines = [
        f"Misma transaccion ({match.strip()}, {fmt_clp(int(amount))}):",
        "",
        f"Canonico — {link_label(canonical)}",
        f"  {fmt_date_dd_mm_yy(canonical.get('movement_date') or '')} | id {canon_id[:12]}…",
        "",
        "Vinculados (correctos pero no cuentan aparte):",
    ]
    for row in linked:
        lines.append(f"• {link_label(row)} — {fmt_date_dd_mm_yy(row.get('movement_date') or '')}")

    lines.extend(
        [
            "",
            "Es un solo pago (ej. arriendo): Gmail/cronjob + screenshot app son la misma operacion.",
            "No eliminar registros; quedaron marcados para no duplicar totales.",
        ]
    )
    summary = "\n".join(lines)
    return {
        "status": "ok",
        "canonical_movement_id": canon_id,
        "linked_count": len(linked),
        "linked_ids": [r.get("movement_id") for r in linked],
        "summary": summary,
        "whatsapp_reply": summary,
    }


def cmd_scan(args: argparse.Namespace) -> Dict[str, Any]:
    csv_path = resolve_data_path(args.csv)
    links_path = resolve_data_path(args.links)
    rows = load_all_rows(csv_path)
    links = load_movimiento_links(links_path)
    seen_groups: set[str] = set()
    groups_out: List[Dict[str, Any]] = []

    salidas = [
        r
        for r in rows
        if int(parse_clp(r.get("amount_clp") or "0") or 0) >= 10_000
        and (
            (r.get("movement_type") or "").startswith("transferencia")
            or (r.get("source") or "") in {"whatsapp_foto", "santander_app"}
        )
    ]

    for row in salidas:
        amt = int(parse_clp(row.get("amount_clp") or "0") or 0)
        hay = normalize_store_name(movement_row_text(row))
        token = hay.split()[0][:12] if hay else "?"
        key = f"{amt}:{token}"
        if key in seen_groups:
            continue
        group = find_duplicate_group(rows, amount_clp=amt, match=token, window_days=args.window_days)
        if len(group) < 2:
            continue
        seen_groups.add(key)
        canon = pick_canonical_transfer(group)
        groups_out.append(
            {
                "amount_clp": amt,
                "match": token,
                "count": len(group),
                "canonical_id": canon.get("movement_id"),
                "sources": sorted({r.get("source") or "?" for r in group}),
                "already_linked": sum(1 for r in group if is_excluded_from_totals(r.get("movement_id") or "", links)),
            }
        )

    lines = [f"Grupos posibles duplicados multi-fuente: {len(groups_out)}"]
    for g in groups_out[:15]:
        lines.append(
            f"• {fmt_clp(g['amount_clp'])} {g['match']} — {g['count']} regs "
            f"({', '.join(g['sources'])}) linked={g['already_linked']}"
        )
    summary = "\n".join(lines)
    return {"status": "ok", "groups": groups_out, "summary": summary, "whatsapp_reply": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Vincular misma transaccion en varias fuentes.")
    parser.add_argument("--csv", default=DEFAULT_UNIFIED_CSV)
    parser.add_argument("--links", default=DEFAULT_MOVIMIENTO_LINKS)
    parser.add_argument("--text", default="", help="Mensaje usuario (monto + contraparte).")

    sub = parser.add_subparsers(dest="command", required=True)
    auto = sub.add_parser("auto-link", help="Vincular duplicados de una transaccion.")
    auto.add_argument("--amount", type=int, default=None)
    auto.add_argument("--match", default="")
    auto.add_argument("--ref", default="", help="Referencia banco ej. 0782993461")
    auto.add_argument("--date", default="", help="YYYY-MM-DD fecha aprox.")
    auto.add_argument("--window-days", type=int, default=10)
    auto.add_argument("--text", default="")
    auto.add_argument("--json", action="store_true")

    scan = sub.add_parser("scan", help="Listar grupos duplicados probables.")
    scan.add_argument("--window-days", type=int, default=10)
    scan.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if args.command == "auto-link":
        result = cmd_auto_link(args)
    else:
        result = cmd_scan(args)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("whatsapp_reply") or result.get("summary") or result.get("message") or "")


if __name__ == "__main__":
    main()
