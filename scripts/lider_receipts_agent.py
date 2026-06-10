import argparse
import base64
import csv
import io
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pypdf import PdfReader

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
ROOT = Path(__file__).resolve().parent.parent

DEFAULT_QUERY = (
    'from:contacto@info.lider.cl '
    '(subject:"Boleta Digital Lider" OR subject:"Boleta electronica") '
    "has:attachment"
)

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

BLOCKED_ATTACHMENT_PATTERNS = (
    "ticket de promoción",
    "ticket de promocion",
    "promocion",
    "promoción",
    "cupon",
    "cupón",
    "ticket de cambio",
    "cambio",
)

BLOCKED_LINE_PATTERNS = (
    "ticket de promoción",
    "ticket de promocion",
    "cupon valido",
    "cupón válido",
    "codigo en caja",
    "código en caja",
    "notrx",
    "local:",
    "caja :",
    "ticket de cambio",
    "codigo:",
    "rf lleve",
    "rf canje",
    "mi club",
    "cliente mi club",
    "compra debito",
    "compra débito",
    "debit/prepag",
    "vuel to",
    "num oper",
    "numero unico",
    "número único",
)


def load_credentials(credentials_file: Path, token_file: Path) -> Credentials:
    creds: Optional[Credentials] = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
            # Server-friendly auth: try local callback first, fallback to console flow.
            try:
                creds = flow.run_local_server(port=0)
            except Exception:
                auth_url, _ = flow.authorization_url(
                    access_type="offline",
                    include_granted_scopes="true",
                    prompt="consent",
                )
                print("Abre esta URL en tu navegador y autoriza la app:")
                print(auth_url)
                code = input("Pega aqui el codigo de autorizacion: ").strip()
                flow.fetch_token(code=code)
                creds = flow.credentials
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_gmail_service(credentials_file: Path, token_file: Path):
    creds = load_credentials(credentials_file, token_file)
    return build("gmail", "v1", credentials=creds)


def load_state(state_file: Path) -> Dict[str, bool]:
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state_file: Path, state: Dict[str, bool]) -> None:
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_parts(parts: List[Dict]) -> List[Dict]:
    extracted: List[Dict] = []
    for part in parts or []:
        if part.get("parts"):
            extracted.extend(extract_parts(part["parts"]))
        else:
            extracted.append(part)
    return extracted


def decode_pdf_content(data: str) -> bytes:
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def parse_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages_text = []
    for page in reader.pages:
        pages_text.append(page.extract_text() or "")
    return "\n".join(pages_text)


def parse_purchase_date(text: str) -> Optional[str]:
    patterns = [
        r"(\d{2}[/-]\d{2}[/-]\d{4})",
        r"(\d{4}[/-]\d{2}[/-]\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            raw = match.group(1).replace("/", "-")
            if len(raw.split("-")[0]) == 4:
                return raw
            day, month, year = raw.split("-")
            return f"{year}-{month}-{day}"
    return None


def parse_purchase_time(text: str) -> Optional[str]:
    # Formato esperado: 13:44:23
    match = re.search(r"\b([01]?\d|2[0-3]):[0-5]\d:[0-5]\d\b", text)
    if not match:
        return None
    return match.group(0)


def parse_purchase_datetime(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    date = parse_purchase_date(text)
    time = parse_purchase_time(text)
    if date and time:
        return date, time, f"{date} {time}"
    return date, time, None


def parse_receipt_number(text: str) -> Optional[str]:
    patterns = [
        r"Bol\.?\s*Electronica\s*:\s*([0-9]{6,})",
        r"Boleta\s*Electronica\s*:\s*([0-9]{6,})",
        r"Boleta\s*:\s*([0-9]{6,})",
        r"NUMERO\s+UNICO\s*:?[\s\r\n]*([0-9]{6,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def parse_store_branch(text: str) -> Optional[str]:
    patterns = [
        r"SUC\s*:\s*([^\n\r]+)",
        r"Suc\s*:\s*([^\n\r]+)",
        r"Local\s*:\s*([^\n\r]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            value = re.sub(r"\s{2,}", " ", value)
            return value[:120]
    return None


def parse_total(text: str) -> Optional[float]:
    candidates = re.findall(r"TOTAL\s*\$?\s*([\d\.\,]+)", text, flags=re.IGNORECASE)
    if not candidates:
        candidates = re.findall(r"\$\s*([\d\.\,]{3,})", text)
    if not candidates:
        return None
    value = candidates[-1].replace(".", "").replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def category_for_product(name: str) -> str:
    lowered = name.lower()
    rules = {
        "frutas_verduras": ["manzana", "platano", "palta", "lechuga", "tomate", "cebolla"],
        "carnes_pescados": ["pollo", "vacuno", "cerdo", "salmon", "atun"],
        "lacteos_huevos": ["leche", "queso", "yogurt", "huevo", "mantequilla"],
        "panaderia": ["pan", "hallulla", "marraqueta", "molde", "tortilla"],
        "limpieza_hogar": ["detergente", "lavaloza", "cloro", "suavizante", "papel higienico"],
        "cuidado_personal": ["shampoo", "jabon", "desodorante", "pasta dental"],
        "bebidas": ["coca", "jugo", "agua", "cerveza", "vino", "bebida"],
        "despensa": ["arroz", "fideo", "aceite", "azucar", "sal", "harina"],
    }
    for category, keywords in rules.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "otros"


def parse_line_items(text: str) -> List[Tuple[str, Optional[float]]]:
    items: List[Tuple[str, Optional[float]]] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        lowered = line.lower()
        if any(token in lowered for token in BLOCKED_LINE_PATTERNS):
            continue
        if len(line) < 4:
            continue
        if re.fullmatch(r"\d{12,14}", line.strip()):
            continue
        # Evita líneas tipo fecha/hora terminal que OCR transforma en números gigantes.
        if re.search(r"\b\d{2}/\d{2}/\d{2}\b", line) and re.search(r"\b\d{2}:\d{2}:\d{2}\b", line):
            continue
        if re.search(r"\b(total|subtotal|iva|rut|boleta|cajero)\b", line, flags=re.IGNORECASE):
            continue
        parsed_amount: Optional[float] = None
        name = line

        # Patrón común OCR: "2X3.590 PRODUCTO $"
        qty_price = re.search(r"\b(\d{1,3})X([\d\.\,]{2,})\b", line, flags=re.IGNORECASE)
        if qty_price:
            qty = float(qty_price.group(1))
            price = float(qty_price.group(2).replace(".", "").replace(",", "."))
            parsed_amount = qty * price
        else:
            # Formatos Lider vistos: "PRODUCTO $ 1.590" y "PRODUCTO 1.590 $".
            amount_match = re.search(r"\$\s*([\d\.\,]{2,})\s*$", line)
            if not amount_match:
                amount_match = re.search(r"([\d\.\,]{2,})\s*\$\s*$", line)
            if amount_match:
                amount = amount_match.group(1).replace(".", "").replace(",", ".")
                try:
                    parsed_amount = float(amount)
                except ValueError:
                    parsed_amount = None

        if parsed_amount is None:
            continue

        # Limpieza de prefijos de código de barra y monto final.
        name = re.sub(r"^\d{12,14}\s+", "", name).strip(" -")
        name = re.sub(r"\s*\$\s*[\d\.\,]+\s*$", "", name).strip(" -")
        name = re.sub(r"\s*[\d\.\,]+\s*\$\s*$", "", name).strip(" -")
        if not name:
            continue
        if parsed_amount <= 0:
            continue
        if parsed_amount > 500000:
            # Guarda alta para boleta supermercado, casi seguro ruido OCR.
            continue
        items.append((name, parsed_amount))
    return items


def is_valid_receipt_attachment(filename: str) -> bool:
    lowered = filename.lower().strip()
    if not lowered.endswith(".pdf"):
        return False
    if any(token in lowered for token in BLOCKED_ATTACHMENT_PATTERNS):
        return False
    # Prioriza boletas, facturas o documentos de compra.
    if any(token in lowered for token in ("boleta", "factura", "compra")):
        return True
    return False


def ensure_csv_headers(csv_file: Path) -> None:
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    if not csv_file.exists():
        with csv_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
        return

    # Migra CSV antiguo agregando columnas faltantes al final.
    with csv_file.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing_columns = reader.fieldnames or []
        if all(col in existing_columns for col in CSV_COLUMNS):
            return
        rows = list(reader)

    merged_columns = list(existing_columns)
    for col in CSV_COLUMNS:
        if col not in merged_columns:
            merged_columns.append(col)

    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=merged_columns)
        writer.writeheader()
        for row in rows:
            for col in merged_columns:
                row.setdefault(col, "")
            writer.writerow(row)


def append_rows(csv_file: Path, rows: List[List]) -> None:
    if not rows:
        return
    with csv_file.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

def send_whatsapp(message: str, target_file: Path, *, dry_run: bool = False) -> Dict[str, Any]:
    target = target_file.read_text(encoding="utf-8").strip() if target_file.exists() else ""
    if not target:
        return {"ok": False, "reason": "missing_whatsapp_target"}

    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "openclaw-gateway",
        "openclaw",
        "message",
        "send",
        "--channel",
        "whatsapp",
        "--target",
        target,
        "--message",
        message,
        "--json",
    ]
    if dry_run:
        cmd.append("--dry-run")

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT / "openclaw"),
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-1000:],
        "stderr": proc.stderr[-1000:],
    }


def append_jsonl(path: Path, item: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def format_receipt_confirmation(receipt: Dict[str, Any]) -> str:
    total = receipt.get("ticket_total")
    total_text = f"CLP {int(total):,}".replace(",", ".") if isinstance(total, (float, int)) else "sin total"
    return "\n".join(
        [
            "✅ Lider: boleta leida y registrada",
            f"Fecha compra: {receipt.get('purchase_datetime') or receipt.get('purchase_date') or 'sin fecha'}",
            f"Sucursal: {receipt.get('store_branch') or 'sin sucursal'}",
            f"Boleta: {receipt.get('receipt_number') or 'sin numero'}",
            f"Total: {total_text}",
            f"Items detectados: {receipt.get('items_count', 0)}",
        ]
    )


def send_receipt_confirmations(
    receipts: List[Dict[str, Any]],
    target_file: Path,
    outbox_file: Path,
    *,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    confirmations: List[Dict[str, Any]] = []
    for receipt in receipts:
        message = format_receipt_confirmation(receipt)
        send_result = send_whatsapp(message, target_file, dry_run=dry_run)
        confirmation = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "message_id": receipt.get("message_id"),
            "receipt_number": receipt.get("receipt_number"),
            "whatsapp": send_result,
            "message": message,
        }
        confirmations.append(confirmation)
        if not send_result.get("ok"):
            append_jsonl(outbox_file, confirmation)
    return confirmations



def process_messages(
    service,
    query: str,
    csv_file: Path,
    state_file: Path,
    max_results: int = 30,
) -> Tuple[int, List[Dict[str, Any]]]:
    state = load_state(state_file)
    ensure_csv_headers(csv_file)
    response = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = response.get("messages", [])
    processed_count = 0
    rows: List[List] = []
    receipts: List[Dict[str, Any]] = []

    for message_stub in messages:
        message_id = message_stub["id"]
        if state.get(message_id):
            continue

        message = (
            service.users().messages().get(userId="me", id=message_id, format="full").execute()
        )
        payload = message.get("payload", {})
        parts = extract_parts(payload.get("parts", []))
        internal_date = datetime.fromtimestamp(int(message.get("internalDate", "0")) / 1000.0)

        for part in parts:
            filename = part.get("filename", "")
            body = part.get("body", {})
            if not is_valid_receipt_attachment(filename):
                continue
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

            pdf_text = parse_pdf_text(decode_pdf_content(data))
            parsed_date, parsed_time, parsed_datetime = parse_purchase_datetime(pdf_text)
            purchase_date = parsed_date or internal_date.strftime("%Y-%m-%d")
            purchase_time = parsed_time or internal_date.strftime("%H:%M:%S")
            purchase_datetime = parsed_datetime or f"{purchase_date} {purchase_time}"
            receipt_number = parse_receipt_number(pdf_text) or ""
            store_branch = parse_store_branch(pdf_text) or ""
            ticket_total = parse_total(pdf_text)
            line_items = parse_line_items(pdf_text)
            if not line_items:
                line_items = [("boleta_sin_detalle_detectado", ticket_total)]

            receipts.append(
                {
                    "message_id": message_id,
                    "purchase_date": purchase_date,
                    "purchase_time": purchase_time,
                    "purchase_datetime": purchase_datetime,
                    "store_branch": store_branch,
                    "receipt_number": receipt_number,
                    "ticket_total": ticket_total,
                    "items_count": len(line_items),
                }
            )

            for product_name, line_amount in line_items:
                rows.append(
                    [
                        datetime.now().isoformat(timespec="seconds"),
                        purchase_date,
                        purchase_time,
                        purchase_datetime,
                        "lider",
                        store_branch,
                        receipt_number,
                        message_id,
                        filename,
                        product_name,
                        category_for_product(product_name),
                        line_amount,
                        ticket_total,
                    ]
                )

        state[message_id] = True
        processed_count += 1

    append_rows(csv_file, rows)
    save_state(state_file, state)
    return processed_count, receipts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lee boletas de Lider desde Gmail y las guarda en CSV."
    )
    parser.add_argument(
        "--credentials",
        default="secrets/gmail_credentials.json",
        help="Ruta a credentials de Google Cloud OAuth.",
    )
    parser.add_argument(
        "--token",
        default="secrets/gmail_token.json",
        help="Ruta al token OAuth local.",
    )
    parser.add_argument(
        "--output",
        default="data/lider_receipts.csv",
        help="CSV de salida con detalle de boletas.",
    )
    parser.add_argument(
        "--state",
        default="data/lider_processed_messages.json",
        help="Archivo de estado para no reprocesar correos.",
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="Consulta Gmail para filtrar boletas.",
    )
    parser.add_argument("--max-results", type=int, default=30)
    parser.add_argument("--target-file", default="secrets/whatsapp_allow_from.txt")
    parser.add_argument("--outbox", default="data/lider_receipts_outbox.jsonl")
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    credentials_file = Path(args.credentials)
    token_file = Path(args.token)
    output_file = Path(args.output)
    state_file = Path(args.state)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    credentials_file.parent.mkdir(parents=True, exist_ok=True)

    if not credentials_file.exists():
        raise FileNotFoundError(
            f"No existe {credentials_file}. Descarga OAuth client desde Google Cloud Console."
        )

    try:
        service = get_gmail_service(credentials_file, token_file)
        processed, receipts = process_messages(
            service=service,
            query=args.query,
            csv_file=output_file,
            state_file=state_file,
            max_results=args.max_results,
        )
        confirmations: List[Dict[str, Any]] = []
        if receipts and not args.no_notify:
            confirmations = send_receipt_confirmations(
                receipts,
                ROOT / args.target_file,
                ROOT / args.outbox,
                dry_run=args.dry_run,
            )
        print(f"Mensajes procesados: {processed}")
        print(f"Confirmaciones enviadas: {sum(1 for item in confirmations if item.get('whatsapp', {}).get('ok'))}")
        print(f"CSV actualizado: {output_file}")
    except HttpError as error:
        raise RuntimeError(f"Error Gmail API: {error}") from error


if __name__ == "__main__":
    main()
