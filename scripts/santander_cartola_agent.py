"""Descarga cartolas mensuales Santander desde Gmail y extrae movimientos del PDF."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lider_receipts_agent import (
    decode_pdf_content,
    extract_parts,
    get_gmail_service,
    load_state,
    save_state,
)

DEFAULT_QUERY = (
    'from:mensajeria@santander.cl subject:"Cartola Mensual" has:attachment newer_than:400d'
)
DEFAULT_PDF_PASSWORD = os.getenv("SANTANDER_CARTOLA_PDF_PASSWORD", "15894150")
DEFAULT_CARTOLA_CSV = "data/santander_cartola.csv"
DEFAULT_STATE = "data/santander_cartola_state.json"

CSV_COLUMNS = [
    "processed_at",
    "message_id",
    "email_date",
    "cartola_number",
    "period_from",
    "period_to",
    "movement_date",
    "branch",
    "description",
    "document_number",
    "charge_clp",
    "credit_clp",
    "balance_clp",
    "pdf_filename",
]

AMOUNT_RE = re.compile(r"(\d{1,3}(?:\.\d{3})*)")
DATE_LINE_RE = re.compile(r"^(\d{2}/\d{2})\s+(.+)$")
PERIOD_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})")
CARTOLA_NUM_RE = re.compile(r"Cartola\s*(?:N[°o.]?\s*)?(\d+)", re.IGNORECASE)
SKIP_LINE_RE = re.compile(
    r"(DETALLE DE MOVIMIENTOS|SALDOS DIARIOS|FECHA\s+SUCURSAL|DESCRIPCION|CHEQUES|DEPOSITOS|"
    r"SALDO INICIAL|INFORMACION DE|SUCURSAL VIRTUAL|WWW\.SANTANDER|Nota:|MENSAJES|"
    r"CTA CTE|CUENTA CORRIENTE|Banco Santander|PAGINA|PÁGINA|µ|CUPO APROBADO)",
    re.IGNORECASE,
)


def parse_clp_token(value: str) -> int:
    digits = re.sub(r"[^\d]", "", value or "")
    return int(digits) if digits else 0


def parse_period(text: str) -> Tuple[str, str]:
    for line in text.splitlines():
        if "CARTOLA" in line.upper() and re.search(r"\d{2}/\d{2}/\d{4}", line):
            dates = PERIOD_RE.findall(line)
            if dates:
                return _ddmmyyyy_to_iso(dates[0][0]), _ddmmyyyy_to_iso(dates[0][1])
    match = PERIOD_RE.search(text.replace("\n", " "))
    if match:
        return _ddmmyyyy_to_iso(match.group(1)), _ddmmyyyy_to_iso(match.group(2))
    return "", ""


def _ddmmyyyy_to_iso(value: str) -> str:
    day, month, year = value.split("/")
    return f"{year}-{month}-{day}"


def infer_movement_date(dd_mm: str, period_from: str, period_to: str) -> str:
    day_s, month_s = dd_mm.split("/")
    day, month = int(day_s), int(month_s)
    candidates: List[str] = []
    for year in {period_from[:4], period_to[:4]}:
        if not year.isdigit():
            continue
        try:
            datetime(int(year), month, day)
            candidates.append(f"{year}-{month_s}-{day_s}")
        except ValueError:
            continue
    if not candidates:
        return ""
    if len(candidates) == 1:
        return candidates[0]
    pf = period_from or candidates[0]
    pt = period_to or candidates[-1]
    for candidate in candidates:
        if pf <= candidate <= pt:
            return candidate
    return candidates[-1]


def parse_pdf_text(pdf_bytes: bytes, password: str) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if reader.is_encrypted:
        result = reader.decrypt(password)
        if result == 0:
            raise ValueError("No se pudo abrir el PDF de cartola (password incorrecta)")
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def is_movement_amount(token: str) -> bool:
    token = token.strip()
    if not token or not re.fullmatch(r"[\d\.]+", token):
        return False
    if "." in token:
        return True
    try:
        return 0 < int(token) < 100000
    except ValueError:
        return False


def classify_movement(description: str) -> Tuple[int, int]:
    """Retorna (charge, credit) segun descripcion."""
    lowered = description.lower()
    if "transf." in lowered and "transf a" not in lowered:
        return 0, 1  # abono entrante
    if any(token in lowered for token in ("anulación", "anulacion", "reverso")):
        return 0, 1
    return 1, 0  # cargo por defecto (compra, transf a, giro)


def parse_movement_line(
    line: str,
    period_from: str,
    period_to: str,
) -> Optional[Dict[str, str]]:
    line = line.strip()
    if not line or SKIP_LINE_RE.search(line):
        return None
    match = DATE_LINE_RE.match(line)
    if not match:
        return None

    dd_mm = match.group(1)
    rest = match.group(2).strip()
    segments = [seg.strip() for seg in re.split(r"\s{4,}", rest) if seg.strip()]
    if not segments:
        return None

    meta = segments[0]
    amount_tokens = [seg for seg in segments[1:] if is_movement_amount(seg)]
    if not amount_tokens:
        return None

    charge_flag, credit_flag = classify_movement(meta)
    charge = 0
    credit = 0
    balance = 0

    if len(amount_tokens) >= 2:
        movement_amount = parse_clp_token(amount_tokens[-2])
        balance = parse_clp_token(amount_tokens[-1])
    else:
        movement_amount = parse_clp_token(amount_tokens[-1])

    if credit_flag:
        credit = movement_amount
    else:
        charge = movement_amount

    branch = ""
    document_number = ""
    description = meta
    tokens = meta.split()
    if len(tokens) >= 2 and re.fullmatch(r"\d{6,12}[Kk]?", tokens[1]):
        branch = tokens[0]
        document_number = tokens[1]
        description = " ".join(tokens[2:]).strip()
    elif tokens and re.match(r"^[A-Za-zÁÉÍÓÚáéíóú]", tokens[0]):
        branch = tokens[0]
        if len(tokens) >= 2 and re.fullmatch(r"\d{6,12}[Kk]?", tokens[1]):
            document_number = tokens[1]
            description = " ".join(tokens[2:]).strip()
        else:
            description = " ".join(tokens[1:]).strip()

    if charge == 0 and credit == 0:
        return None

    movement_date = infer_movement_date(dd_mm, period_from, period_to)
    return {
        "movement_date": movement_date,
        "branch": branch,
        "description": description,
        "document_number": document_number,
        "charge_clp": str(charge) if charge else "",
        "credit_clp": str(credit) if credit else "",
        "balance_clp": str(balance) if balance else "",
    }


def parse_cartola_text(text: str) -> Tuple[str, str, str, List[Dict[str, str]]]:
    period_from, period_to = parse_period(text)
    cartola_match = CARTOLA_NUM_RE.search(text)
    cartola_number = cartola_match.group(1) if cartola_match else ""

    movements: List[Dict[str, str]] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        parsed = parse_movement_line(raw_line, period_from, period_to)
        if not parsed:
            continue
        key = "|".join(
            [
                parsed["movement_date"],
                parsed.get("document_number", ""),
                parsed.get("description", ""),
                parsed.get("charge_clp", ""),
                parsed.get("credit_clp", ""),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        movements.append(parsed)
    return period_from, period_to, cartola_number, movements


def is_cartola_pdf(filename: str) -> bool:
    lowered = (filename or "").lower()
    return lowered.endswith(".pdf") and ("cartola" in lowered or lowered.startswith("1_"))


def ensure_csv_headers(csv_file: Path) -> None:
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    if csv_file.exists():
        return
    with csv_file.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(CSV_COLUMNS)


def append_rows(csv_file: Path, rows: List[List[str]]) -> None:
    if not rows:
        return
    with csv_file.open("a", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def process_messages(
    service: Any,
    query: str,
    csv_file: Path,
    state_file: Path,
    password: str,
    max_results: int = 20,
) -> int:
    state = load_state(state_file)
    ensure_csv_headers(csv_file)
    response = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = response.get("messages", [])
    processed_count = 0
    rows: List[List[str]] = []

    for message_stub in messages:
        message_id = message_stub["id"]
        if state.get(message_id):
            continue

        message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        payload = message.get("payload", {})
        parts = extract_parts(payload.get("parts", []))
        internal_date = datetime.fromtimestamp(int(message.get("internalDate", "0")) / 1000.0)
        email_date = internal_date.strftime("%Y-%m-%d")

        found_pdf = False
        for part in parts:
            filename = part.get("filename", "")
            if not is_cartola_pdf(filename):
                continue
            body = part.get("body", {})
            if "attachmentId" in body:
                attachment = (
                    service.users()
                    .messages()
                    .attachments()
                    .get(userId="me", messageId=message_id, id=body["attachmentId"])
                    .execute()
                )
                data = attachment.get("data")
            else:
                data = body.get("data")
            if not data:
                continue

            pdf_bytes = decode_pdf_content(data)
            pdf_text = parse_pdf_text(pdf_bytes, password)
            period_from, period_to, cartola_number, movements = parse_cartola_text(pdf_text)
            if not movements:
                continue

            found_pdf = True
            stamp = datetime.now().isoformat(timespec="seconds")
            for movement in movements:
                rows.append(
                    [
                        stamp,
                        message_id,
                        email_date,
                        cartola_number,
                        period_from,
                        period_to,
                        movement["movement_date"],
                        movement["branch"],
                        movement["description"],
                        movement["document_number"],
                        movement["charge_clp"],
                        movement["credit_clp"],
                        movement["balance_clp"],
                        filename,
                    ]
                )

        if found_pdf:
            state[message_id] = True
            processed_count += 1

    append_rows(csv_file, rows)
    save_state(state_file, state)
    return processed_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrae movimientos de cartolas Santander (Gmail PDF).")
    parser.add_argument("--credentials", default="secrets/gmail_credentials.json")
    parser.add_argument("--token", default="secrets/gmail_token.json")
    parser.add_argument("--output", default=DEFAULT_CARTOLA_CSV)
    parser.add_argument("--state", default=DEFAULT_STATE)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--password", default=DEFAULT_PDF_PASSWORD)
    parser.add_argument("--max-results", type=int, default=20)
    parser.add_argument("--reset", action="store_true", help="Borra CSV y state antes de procesar.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output = Path(args.output)
    state_path = Path(args.state)
    if args.reset:
        output.unlink(missing_ok=True)
        state_path.unlink(missing_ok=True)
    service = get_gmail_service(Path(args.credentials), Path(args.token))
    count = process_messages(
        service,
        args.query,
        output,
        state_path,
        password=args.password,
        max_results=args.max_results,
    )
    result = {"processed_messages": count, "output": args.output}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Cartolas procesadas: {count}")
        print(f"CSV: {args.output}")


if __name__ == "__main__":
    main()
