"""Observaciones por movimiento (notas que no vienen del banco)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import (
    DEFAULT_OBSERVACIONES,
    DEFAULT_UNIFIED_CSV,
    find_movements,
    load_observaciones,
    movement_label,
    parse_clp,
    resolve_data_path,
    save_observaciones,
)
from finanzas_merchant_report import fmt_clp, fmt_date_dd_mm_yy, load_all_rows


def format_match_line(row: Dict[str, str], note: str = "") -> str:
    iso = row.get("movement_date") or ""
    amount = int(parse_clp(row.get("amount_clp") or "0") or 0)
    label = movement_label(row)
    line = f"{fmt_date_dd_mm_yy(iso)} — {fmt_clp(amount)} — {label}"
    if note:
        line += f" — Obs: {note}"
    return line


def cmd_set(args: argparse.Namespace) -> Dict[str, Any]:
    csv_path = resolve_data_path(args.csv)
    obs_path = resolve_data_path(args.observaciones)
    rows = load_all_rows(csv_path)
    notes = load_observaciones(obs_path)

    movement_id = (args.movement_id or "").strip()
    candidates: List[Dict[str, str]] = []
    if movement_id:
        candidates = find_movements(rows, movement_id=movement_id)
    else:
        amount = parse_clp(str(args.amount)) if args.amount is not None else None
        if amount is not None:
            amount = int(amount)
        candidates = find_movements(
            rows,
            movement_date=args.date or "",
            amount_clp=amount,
            counterparty_contains=args.match or "",
            movement_type=args.movement_type or "",
            description_contains=args.description or "",
        )

    if not candidates:
        return {
            "status": "not_found",
            "message": "No hay movimiento que coincida. Usa fecha YYYY-MM-DD, monto y nombre (ej. --match yanara).",
        }
    if len(candidates) > 1 and not movement_id:
        return {
            "status": "ambiguous",
            "message": f"Hay {len(candidates)} movimientos. Indica mas datos o usa --movement-id.",
            "candidates": [
                {
                    "movement_id": r.get("movement_id"),
                    "line": format_match_line(r, notes.get(r.get("movement_id") or "", {}).get("note", "")),
                }
                for r in candidates[:10]
            ],
        }

    row = candidates[0]
    mid = row.get("movement_id") or ""
    note_text = (args.note or "").strip()
    if not mid:
        return {"status": "error", "message": "Movimiento sin movement_id."}
    if not note_text:
        return {"status": "error", "message": "Falta --note."}

    notes[mid] = {
        "note": note_text,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "movement_date": row.get("movement_date") or "",
        "amount_clp": str(int(parse_clp(row.get("amount_clp") or "0") or 0)),
        "label": movement_label(row),
        "movement_type": row.get("movement_type") or "",
    }
    save_observaciones(obs_path, notes)
    return {
        "status": "ok",
        "movement_id": mid,
        "summary": f"Observacion guardada: {format_match_line(row, note_text)}",
        "note": note_text,
    }


def cmd_clear(args: argparse.Namespace) -> Dict[str, Any]:
    obs_path = resolve_data_path(args.observaciones)
    notes = load_observaciones(obs_path)
    mid = (args.movement_id or "").strip()
    if not mid:
        return {"status": "error", "message": "Falta --movement-id."}
    if mid not in notes:
        return {"status": "not_found", "message": "Sin observacion para ese movement_id."}
    del notes[mid]
    save_observaciones(obs_path, notes)
    return {"status": "ok", "message": "Observacion eliminada.", "movement_id": mid}


def cmd_get(args: argparse.Namespace) -> Dict[str, Any]:
    obs_path = resolve_data_path(args.observaciones)
    notes = load_observaciones(obs_path)
    if args.movement_id:
        entry = notes.get(args.movement_id)
        if not entry:
            return {"status": "not_found", "movement_id": args.movement_id}
        return {"status": "ok", "movement_id": args.movement_id, **entry}
    listed = [
        {"movement_id": mid, **entry}
        for mid, entry in sorted(notes.items(), key=lambda x: x[1].get("updated_at", ""), reverse=True)
    ]
    return {"status": "ok", "count": len(listed), "notes": listed[:50]}


def main() -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--csv", default=DEFAULT_UNIFIED_CSV)
    common.add_argument("--observaciones", default=DEFAULT_OBSERVACIONES)

    parser = argparse.ArgumentParser(description="Notas/observaciones en movimientos financieros.")
    sub = parser.add_subparsers(dest="command", required=True)

    set_p = sub.add_parser("set", help="Guardar o actualizar observacion.", parents=[common])
    set_p.add_argument("--movement-id", default="")
    set_p.add_argument("--date", default="", help="YYYY-MM-DD o DD-MM-YY")
    set_p.add_argument("--amount", type=int, default=None)
    set_p.add_argument("--match", default="", help="Texto en contraparte/descripcion (ej. yanara).")
    set_p.add_argument("--description", default="")
    set_p.add_argument("--movement-type", default="", help="ej. transferencia_salida")
    set_p.add_argument("--note", required=True)
    set_p.add_argument("--json", action="store_true")

    clear_p = sub.add_parser("clear", help="Quitar observacion.", parents=[common])
    clear_p.add_argument("--movement-id", required=True)
    clear_p.add_argument("--json", action="store_true")

    get_p = sub.add_parser("get", help="Leer observacion(es).", parents=[common])
    get_p.add_argument("--movement-id", default="")
    get_p.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if args.command == "set":
        result = cmd_set(args)
    elif args.command == "clear":
        result = cmd_clear(args)
    else:
        result = cmd_get(args)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("summary") or result.get("message") or json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
