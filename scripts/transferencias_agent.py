"""Extrae comprobantes de transferencia Santander desde Gmail (como lider_receipts_agent)."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import re
from datetime import datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from runtime_paths import resolve_repo_path

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

DEFAULT_QUERY = (
    'from:mensajeria@santander.cl '
    'subject:"Comprobante Transferencia de fondos" newer_than:365d'
)

CSV_COLUMNS = [
    "processed_at",
    "message_id",
    "email_date",
    "transfer_date",
    "amount_clp",
    "origin_account_type",
    "origin_account_number",
    "origin_rut",
    "origin_name",
    "destination_name",
    "destination_rut",
    "destination_bank",
    "destination_account_type",
    "destination_account_number",
    "destination_email",
    "comment",
    "raw_subject",
]

SECTION_STOP_LABELS = (
    "datos de destino",
    "antes de imprimir este correo electrónico",
    "nota: este e-mail es generado",
)

FOOTER_MARKERS = (
    "antes de imprimir este correo electrónico",
    "nota: este e-mail es generado",
    "infórmese sobre la garantía",
    "informese sobre la garantia",
)


def load_credentials(credentials_file: Path, token_file: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds: Optional[Credentials] = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
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
    from googleapiclient.discovery import build

    creds = load_credentials(credentials_file, token_file)
    return build("gmail", "v1", credentials=creds)


def load_state(state_file: Path) -> Dict[str, Any]:
    if not state_file.exists():
        return {"messages": {}, "fingerprints": {}}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"messages": {}, "fingerprints": {}}
    if isinstance(data, dict) and "messages" not in data:
        return {"messages": data, "fingerprints": {}}
    return data


def save_state(state_file: Path, state: Dict[str, Any]) -> None:
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_csv_headers(csv_file: Path) -> None:
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    if csv_file.exists():
        return
    with csv_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)


def normalize_html_payload(html: str) -> str:
    """Quita quoted-printable (=3D, saltos soft) antes de parsear."""
    text = re.sub(r"=\r?\n", "", html)
    return text.replace("=3D", "=").replace("=09", "\t")


def extract_parts(parts: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    for part in parts or []:
        if part.get("parts"):
            out.extend(extract_parts(part["parts"]))
        else:
            out.append(part)
    return out


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
    d, m, y = match.group(1).split("/")
    return f"{y}-{m}-{d}"


def normalize_lines(text: str) -> List[str]:
    lines: List[str] = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        if any(marker in line.lower() for marker in FOOTER_MARKERS):
            break
        lines.append(line)
    return lines


def parse_label_value_section(section_lines: List[str]) -> Dict[str, str]:
    data: Dict[str, str] = {}
    i = 0
    while i < len(section_lines):
        label = section_lines[i].strip()
        if not label or len(label) > 40:
            i += 1
            continue
        if i + 1 < len(section_lines):
            nxt = section_lines[i + 1].strip()
            if nxt and not _looks_like_label(nxt):
                data[label.lower()] = nxt
                i += 2
                continue
        i += 1
    return data


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


def extract_section(lines: List[str], start_label: str, stop_labels: tuple[str, ...]) -> List[str]:
    start_idx = None
    for i, line in enumerate(lines):
        if line.lower() == start_label.lower():
            start_idx = i + 1
            break
    if start_idx is None:
        return []
    out: List[str] = []
    for line in lines[start_idx:]:
        if any(line.lower() == s.lower() for s in stop_labels):
            break
        out.append(line)
    return out


def _td_plain_text(td) -> str:
    return re.sub(r"\s+", " ", td.get_text(" ", strip=True)).strip()


def parse_table_pairs_in_section(soup: BeautifulSoup, section_title: str) -> Dict[str, str]:
    """Lee filas <tr> con dos <td> hermanos (label | valor), sin celdas anidadas."""
    data: Dict[str, str] = {}
    in_section = False
    title_lower = section_title.lower()
    for tr in soup.find_all("tr"):
        direct_tds = tr.find_all("td", recursive=False)
        if len(direct_tds) == 1:
            header = _td_plain_text(direct_tds[0])
            if title_lower in header.lower() and "datos de" in header.lower():
                in_section = True
                continue
            if in_section and any(stop in header.lower() for stop in SECTION_STOP_LABELS):
                break
            continue
        if not in_section or len(direct_tds) < 2:
            continue
        label = _td_plain_text(direct_tds[0])
        value = _td_plain_text(direct_tds[-1])
        if not label or not value or label.lower() == value.lower():
            continue
        if any(stop in label.lower() for stop in SECTION_STOP_LABELS):
            break
        if _looks_like_label(label) or len(label) <= 40:
            data[label.lower()] = value
    return data


def pick(data: Dict[str, str], *keys: str) -> str:
    for key in keys:
        if key.lower() in data and data[key.lower()]:
            return data[key.lower()]
    return ""


def first_email(text: str) -> str:
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return match.group(0) if match else ""


def transfer_fingerprint(fields: Dict[str, str]) -> str:
    parts = [
        fields.get("transfer_date") or "",
        fields.get("amount_clp") or "",
        fields.get("destination_rut") or "",
        fields.get("destination_account_number") or "",
        fields.get("destination_bank") or "",
    ]
    return "|".join(parts)


def parse_transfer_fields(html: str) -> Dict[str, str]:
    html = normalize_html_payload(html)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"[ \t]+", " ", text)
    lines = normalize_lines(text)

    origen = parse_table_pairs_in_section(soup, "Datos de origen")
    destino = parse_table_pairs_in_section(soup, "Datos de destino")
    if not origen:
        origen = parse_label_value_section(
            extract_section(lines, "Datos de origen", ("Datos de destino",))
        )
    if not destino:
        destino_lines = extract_section(lines, "Datos de destino", FOOTER_MARKERS)
        destino = parse_label_value_section(destino_lines)

    amount = parse_amount_from_text(text)
    if not amount:
        for strong in soup.find_all("strong"):
            strong_text = strong.get_text(" ", strip=True)
            if "$" in strong_text:
                amount = parse_amount_from_text(strong_text)
                if amount:
                    break

    return {
        "transfer_date": parse_transfer_date(text),
        "amount_clp": str(amount or ""),
        "origin_account_type": pick(origen, "tipo de cuenta"),
        "origin_account_number": pick(origen, "n° de cuenta", "nº de cuenta", "no de cuenta"),
        "origin_rut": pick(origen, "rut"),
        "origin_name": pick(origen, "nombre"),
        "destination_name": pick(destino, "nombre"),
        "destination_rut": pick(destino, "rut"),
        "destination_bank": pick(destino, "banco"),
        "destination_account_type": pick(destino, "tipo de cuenta"),
        "destination_account_number": pick(destino, "n° de cuenta", "nº de cuenta", "no de cuenta"),
        "destination_email": first_email("\n".join(extract_section(lines, "Datos de destino", FOOTER_MARKERS))),
        "comment": pick(origen, "comentario"),
    }


def get_header_value(payload_headers: List[Dict], name: str) -> str:
    for header in payload_headers or []:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def extract_html_from_message(payload: Dict) -> str:
    parts = extract_parts(payload.get("parts", []))
    for part in parts:
        if part.get("mimeType") == "text/html":
            data = part.get("body", {}).get("data")
            if data:
                return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")
    if payload.get("mimeType") == "text/html":
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")
    return ""


def list_message_ids(service, query: str, max_results: int) -> List[str]:
    ids: List[str] = []
    page_token: Optional[str] = None
    while len(ids) < max_results:
        batch = min(100, max_results - len(ids))
        kwargs: Dict[str, Any] = {"userId": "me", "q": query, "maxResults": batch}
        if page_token:
            kwargs["pageToken"] = page_token
        response = service.users().messages().list(**kwargs).execute()
        for item in response.get("messages", []):
            ids.append(item["id"])
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return ids


def row_from_message(full: Dict, fields: Dict[str, str]) -> Dict[str, str]:
    payload = full.get("payload", {})
    internal_date = datetime.fromtimestamp(int(full.get("internalDate", "0")) / 1000.0)
    subject = get_header_value(payload.get("headers", []), "Subject")
    return {
        "processed_at": datetime.now().isoformat(timespec="seconds"),
        "message_id": full.get("id", ""),
        "email_date": internal_date.strftime("%Y-%m-%d %H:%M:%S"),
        "raw_subject": subject,
        **fields,
    }


def process_messages(
    service,
    query: str,
    csv_file: Path,
    state_file: Path,
    max_results: int = 200,
) -> Dict[str, Any]:
    state = load_state(state_file)
    messages_state: Dict[str, bool] = state.setdefault("messages", {})
    fingerprints: Dict[str, bool] = state.setdefault("fingerprints", {})
    ensure_csv_headers(csv_file)

    rows: List[Dict[str, str]] = []
    skipped = 0

    for msg_id in list_message_ids(service, query, max_results):
        if messages_state.get(msg_id):
            continue

        full = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        html = extract_html_from_message(full.get("payload", {}))
        if not html:
            messages_state[msg_id] = True
            skipped += 1
            continue

        fields = parse_transfer_fields(html)
        if not fields.get("amount_clp"):
            messages_state[msg_id] = True
            skipped += 1
            continue

        fp = transfer_fingerprint(fields)
        if fp and fingerprints.get(fp):
            messages_state[msg_id] = True
            skipped += 1
            continue

        row = row_from_message(full, fields)
        rows.append(row)
        messages_state[msg_id] = True
        if fp:
            fingerprints[fp] = True

    if rows:
        with csv_file.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writerows(rows)

    save_state(state_file, state)
    return {
        "processed": len(rows),
        "skipped": skipped,
        "csv": str(csv_file),
        "state": str(state_file),
        "last_rows": rows[-5:],
    }


def parse_eml_file(eml_path: Path) -> Dict[str, str]:
    msg = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())
    html = ""
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            html = part.get_content()
            break
    if not html:
        raise ValueError(f"Sin HTML en {eml_path}")
    fields = parse_transfer_fields(html)
    return {
        "processed_at": datetime.now().isoformat(timespec="seconds"),
        "message_id": f"eml:{eml_path.name}",
        "email_date": "",
        "raw_subject": msg.get("Subject", ""),
        **fields,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Job Gmail: comprobantes Santander 'Transferencia de fondos' -> CSV salidas."
    )
    parser.add_argument("--credentials", default="secrets/gmail_credentials.json")
    parser.add_argument("--token", default="secrets/gmail_token.json")
    parser.add_argument("--output", default="data/transferencias.csv")
    parser.add_argument("--state", default="data/transferencias_state.json")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--max-results", type=int, default=200)
    parser.add_argument("--parse-eml", help="Probar parser con un .eml local (sin Gmail)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output_file = Path(args.output)
    state_file = Path(args.state)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.parent.mkdir(parents=True, exist_ok=True)

    if args.parse_eml:
        row = parse_eml_file(Path(args.parse_eml))
        if args.json:
            print(json.dumps(row, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(row, ensure_ascii=False, indent=2))
        return

    credentials_file = resolve_repo_path(args.credentials)
    token_file = resolve_repo_path(args.token)

    try:
        from googleapiclient.errors import HttpError

        service = get_gmail_service(credentials_file, token_file)
        result = process_messages(
            service=service,
            query=args.query,
            csv_file=output_file,
            state_file=state_file,
            max_results=args.max_results,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Transferencias nuevas: {result['processed']}")
            print(f"Omitidos (ya vistos/sin monto): {result['skipped']}")
            print(f"CSV: {result['csv']}")
    except HttpError as error:
        raise RuntimeError(f"Error Gmail API: {error}") from error


if __name__ == "__main__":
    main()
