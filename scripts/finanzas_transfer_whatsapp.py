"""Registra transferencias desde correo Santander pegado en WhatsApp/Telegram."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import (
    DEFAULT_UNIFIED_CSV,
    dedupe_rows,
    make_movement_id,
    normalize_rut,
    resolve_data_path,
    write_unified_csv,
)
from finanzas_merchant_report import fmt_clp, fmt_date_dd_mm_yy, load_all_rows

FOOTER_MARKERS = (
    "antes de imprimir este correo electrónico",
    "nota: este e-mail es generado",
    "infórmese sobre la garantía",
    "informese sobre la garantia",
)


def parse_amount_from_text(text: str) -> Optional[int]:
    match = re.search(
        r"Monto\s+transferido[\s\S]{0,120}?\$\s*([0-9][0-9\.\,]*)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(r"\$\s*([0-9][0-9\.\,]*)", text)
    if not match:
        return None
    value = match.group(1).replace(".", "").replace(",", "").strip()
    return int(value) if value.isdigit() else None


def parse_transfer_date(text: str) -> str:
    match = re.search(r"realizada el\s+(\d{2}/\d{2}/\d{4})", text, flags=re.IGNORECASE)
    if not match:
        return ""
    day, month, year = match.group(1).split("/")
    return f"{year}-{month}-{day}"


def normalize_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        if any(marker in line.lower() for marker in FOOTER_MARKERS):
            break
        lines.append(line)
    return lines


def _looks_like_label(text: str) -> bool:
    known = {
        "tipo de cuenta",
        "n° de cuenta",
        "nº de cuenta",
        "no de cuenta",
        "rut",
        "nombre",
        "banco",
        "comentario",
        "e-mail",
        "email",
    }
    return text.lower() in known


def parse_label_value_section(section_lines: list[str]) -> Dict[str, str]:
    data: Dict[str, str] = {}
    index = 0
    while index < len(section_lines):
        label = section_lines[index].strip()
        if not label or len(label) > 40:
            index += 1
            continue
        if index + 1 < len(section_lines):
            nxt = section_lines[index + 1].strip()
            if nxt and not _looks_like_label(nxt):
                data[label.lower()] = nxt
                index += 2
                continue
        index += 1
    return data


def extract_section(lines: list[str], start_label: str, stop_labels: tuple[str, ...]) -> list[str]:
    start_idx = None
    for i, line in enumerate(lines):
        if line.lower() == start_label.lower():
            start_idx = i + 1
            break
    if start_idx is None:
        return []
    out: list[str] = []
    for line in lines[start_idx:]:
        if any(line.lower() == stop.lower() for stop in stop_labels):
            break
        out.append(line)
    return out


def pick(data: Dict[str, str], *keys: str) -> str:
    for key in keys:
        if key.lower() in data and data[key.lower()]:
            return data[key.lower()]
    return ""


TRANSFER_EMAIL_HINT = re.compile(
    r"(mensajeria@santander|@santander\.cl|"
    r"monto\s+transferido|comprobante\s+transferencia|"
    r"datos\s+de\s+origen|datos\s+de\s+destino|"
    r"notificaci[oó]n\s+de\s+transferencia|"
    r"transferencia\s+de\s+fondos|realizada\s+el\s+\d{2}/\d{2}/\d{4})",
    re.I | re.S,
)

INCOMING_HINT = re.compile(
    r"(recibid|abono\s+en\s+(?:tu\s+)?cuenta|ingreso\s+(?:a\s+tu\s+)?cuenta|"
    r"te\s+informamos\s+que|ha\s+realizado\s+una\s+transferencia|"
    r"transferencia\s+a\s+tu\s+cuenta|datos\s+del\s+ordenante|ordenante|"
    r"notificaci[oó]n\s+de\s+transferencia)",
    re.I,
)

OUTGOING_HINT = re.compile(
    r"(comprobante\s+transferencia\s+de\s+fondos|datos\s+de\s+origen\s+.*datos\s+de\s+destino)",
    re.I | re.S,
)


def looks_like_transfer_email(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 80:
        return False
    return bool(TRANSFER_EMAIL_HINT.search(t))


def parse_amount_extended(text: str) -> Optional[int]:
    amount = parse_amount_from_text(text)
    if amount:
        return amount
    patterns = (
        r"por\s+un\s+monto\s+de\s+\$\s*([0-9][0-9\.\,]*)",
        r"monto[:\s]+\$\s*([0-9][0-9\.\,]*)",
        r"abono[^$\n]{0,60}\$\s*([0-9][0-9\.\,]*)",
        r"transferencia[^$\n]{0,60}\$\s*([0-9][0-9\.\,]*)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).replace(".", "").replace(",", "").strip()
        if value.isdigit():
            return int(value)
    return None


def parse_ordenante_plain(text: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    rut_match = re.search(
        r"RUT\s*[:\-]\s*([0-9]{1,2}\.?[0-9]{3}\.?[0-9]{3}-[0-9kK])",
        text,
        flags=re.IGNORECASE,
    )
    if rut_match:
        data["rut"] = rut_match.group(1).strip()
    name_match = re.search(
        r"(?:Nombre|Ordenante|Remitente)\s*[:\-]\s*([^\n\r]+?)(?:\s+RUT\s*[:\-]|$)",
        text,
        flags=re.IGNORECASE,
    )
    if name_match:
        data["nombre"] = name_match.group(1).strip()
    bank_match = re.search(r"Banco\s*[:\-]\s*([^\n\r]+)", text, flags=re.IGNORECASE)
    if bank_match:
        data["banco"] = bank_match.group(1).strip()
    section = re.search(
        r"datos\s+del\s+ordenante([\s\S]{0,500}?)(?:realizada|antes\s+de\s+imprimir|nota:)",
        text,
        flags=re.IGNORECASE,
    )
    if section:
        block = parse_label_value_section(normalize_lines(section.group(1)))
        for k, v in block.items():
            if "nombre" in k and "nombre" not in data:
                data["nombre"] = v
            if k == "rut" and "rut" not in data:
                data["rut"] = v
            if "banco" in k and "banco" not in data:
                data["banco"] = v
    return data


def parse_transfer_paste(text: str) -> Dict[str, str]:
    lowered = text.lower()
    if "<td" in lowered or "<table" in lowered:
        try:
            from transferencias_agent import parse_transfer_fields

            fields = parse_transfer_fields(text)
        except ImportError:
            fields = {}
    else:
        lines = normalize_lines(text)
        origen = parse_label_value_section(
            extract_section(lines, "Datos de origen", ("Datos de destino",))
        )
        destino = parse_label_value_section(
            extract_section(lines, "Datos de destino", FOOTER_MARKERS)
        )
        ordenante = parse_ordenante_plain(text)
        fields = {
            "transfer_date": parse_transfer_date(text),
            "amount_clp": "",
            "origin_rut": pick(origen, "rut") or ordenante.get("rut", ""),
            "origin_name": pick(origen, "nombre") or ordenante.get("nombre", ""),
            "destination_rut": pick(destino, "rut"),
            "destination_name": pick(destino, "nombre"),
            "destination_bank": pick(destino, "banco") or ordenante.get("banco", ""),
            "comment": pick(origen, "comentario"),
        }
    amount = parse_amount_extended(text)
    if amount:
        fields["amount_clp"] = str(amount)
    elif fields.get("amount_clp") and str(fields["amount_clp"]).isdigit():
        pass
    else:
        parsed = parse_amount_from_text(text)
        if parsed:
            fields["amount_clp"] = str(parsed)
    return fields


def classify_direction(text: str, fields: Dict[str, str], owner_rut: str) -> str:
    owner = normalize_rut(owner_rut)
    dest = normalize_rut(fields.get("destination_rut") or "")
    orig = normalize_rut(fields.get("origin_rut") or "")

    if owner:
        if dest == owner:
            return "transferencia_entrada"
        if orig == owner and dest and dest != owner:
            return "transferencia_salida"

    if INCOMING_HINT.search(text):
        return "transferencia_entrada"

    if OUTGOING_HINT.search(text) and fields.get("destination_name"):
        if owner and dest == owner:
            return "transferencia_entrada"
        return "transferencia_salida"

    # Correo de notificación al beneficiario (sin bloques origen/destino completos).
    if fields.get("origin_name") and not fields.get("destination_name"):
        return "transferencia_entrada"

    return "transferencia_entrada" if INCOMING_HINT.search(text) else "transferencia_salida"


def build_unified_row(
    fields: Dict[str, str],
    movement_type: str,
    text: str,
) -> Dict[str, str]:
    amount = int(fields.get("amount_clp") or 0)
    is_in = movement_type == "transferencia_entrada"
    counterparty = (
        fields.get("origin_name") if is_in else fields.get("destination_name")
    ) or ""
    counterparty_rut = (
        fields.get("origin_rut") if is_in else fields.get("destination_rut")
    ) or ""
    bank = fields.get("destination_bank") or ""
    transfer_date = fields.get("transfer_date") or ""

    if is_in:
        description = f"Transferencia recibida de {counterparty}".strip()
    else:
        description = f"Transferencia a {counterparty}".strip()
    if bank:
        description += f" ({bank})"
    if fields.get("comment"):
        description += f" — {fields['comment']}"

    subject_match = re.search(r"asunto:\s*([^\n]+)", text, flags=re.IGNORECASE)
    raw_subject = subject_match.group(1).strip() if subject_match else text[:120]

    movement_id = make_movement_id(
        "whatsapp_email",
        movement_type,
        amount,
        transfer_date,
        counterparty_rut,
        counterparty,
    )

    now = datetime.now().isoformat(timespec="seconds")
    return {
        "processed_at": now,
        "movement_id": movement_id,
        "movement_type": movement_type,
        "source": "whatsapp_email",
        "movement_date": transfer_date,
        "movement_time": "",
        "movement_datetime": transfer_date or now,
        "merchant": "santander",
        "merchant_rut": "",
        "merchant_branch": "",
        "document_number": "",
        "reference_id": "",
        "description": description,
        "category": "transferencias",
        "amount_clp": str(amount),
        "ticket_total": str(amount),
        "payment_method": "transferencia",
        "counterparty": counterparty,
        "counterparty_rut": counterparty_rut,
        "raw_source_file": raw_subject,
    }


def register_movement(unified_csv: Path, row: Dict[str, str]) -> str:
    rows = load_all_rows(unified_csv)
    movement_id = row.get("movement_id") or ""
    if movement_id and any(existing.get("movement_id") == movement_id for existing in rows):
        return "duplicate"
    rows.append(row)
    write_unified_csv(unified_csv, dedupe_rows(rows))
    return "new"


def format_reply(
    *,
    status: str,
    movement_type: str,
    fields: Dict[str, str],
    register_status: str = "",
) -> str:
    amount = int(fields.get("amount_clp") or 0)
    counterparty = fields.get("origin_name") or fields.get("destination_name") or "desconocido"
    date_label = fmt_date_dd_mm_yy(fields.get("transfer_date") or "")

    if status == "error":
        return (
            "Reconocí un correo de Santander pero no pude leer el monto. "
            "Reenvía el correo completo o escribe: /fin me transfirieron $X de NOMBRE"
        )

    direction = "entrante" if movement_type == "transferencia_entrada" else "saliente"
    if register_status == "duplicate":
        lines = [
            f"Esa transferencia {direction} ya estaba registrada:",
            f"Monto: {fmt_clp(amount)}",
            f"Contraparte: {counterparty}",
        ]
    else:
        lines = [
            f"Transferencia {direction} registrada:",
            f"Monto: {fmt_clp(amount)}",
            f"{'De' if movement_type == 'transferencia_entrada' else 'Para'}: {counterparty}",
        ]
    if date_label:
        lines.append(f"Fecha: {date_label}")
    return "\n".join(lines)


def process_transfer_email(
    text: str,
    *,
    unified_csv: Path | None = None,
    owner_rut: str = "",
) -> Dict[str, Any]:
    if not looks_like_transfer_email(text):
        return {"status": "skip", "agent": "fin", "whatsapp_reply": ""}

    owner = owner_rut or os.getenv("FINANZAS_OWNER_RUT", "")
    csv_path = unified_csv or resolve_data_path(DEFAULT_UNIFIED_CSV)
    fields = parse_transfer_paste(text)
    amount = int(fields.get("amount_clp") or 0)
    if amount <= 0:
        return {
            "status": "error",
            "agent": "fin",
            "whatsapp_reply": format_reply(status="error", movement_type="", fields=fields),
            "parsed": fields,
        }

    movement_type = classify_direction(text, fields, owner)
    row = build_unified_row(fields, movement_type, text)
    register_status = register_movement(csv_path, row)

    return {
        "status": "ok",
        "agent": "fin",
        "register_status": register_status,
        "movement_type": movement_type,
        "parsed": fields,
        "whatsapp_reply": format_reply(
            status="ok",
            movement_type=movement_type,
            fields=fields,
            register_status=register_status,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Correo Santander pegado -> CSV + whatsapp_reply.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--unified-csv", default="")
    parser.add_argument("--owner-rut", default=os.getenv("FINANZAS_OWNER_RUT", ""))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    unified = Path(args.unified_csv) if args.unified_csv else None
    result = process_transfer_email(
        args.text,
        unified_csv=unified,
        owner_rut=args.owner_rut,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("whatsapp_reply", ""))
    if result.get("status") == "error":
        sys.exit(1)
    if result.get("status") == "skip":
        sys.exit(2)


if __name__ == "__main__":
    main()
