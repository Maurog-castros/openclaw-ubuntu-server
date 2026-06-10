"""Monitor Gmail: clasifica correos importantes y avisa por WhatsApp."""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import subprocess
import sys
from datetime import datetime
from email.header import decode_header, make_header
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
ROOT = Path(__file__).resolve().parent.parent

DEFAULT_RULES = {
    "categories": [
        {
            "id": "entrevista_trabajo",
            "label": "entrevista/trabajo",
            "priority": 100,
            "keywords": [
                "entrevista",
                "interview",
                "seleccion",
                "selección",
                "reclutamiento",
                "recruiter",
                "talent acquisition",
                "oferta laboral",
                "job opportunity",
                "postulacion",
                "postulación",
                "vacante",
                "cv",
                "curriculum",
                "linkedin",
            ],
            "senders": [],
        },
        {
            "id": "legal",
            "label": "legal/abogado",
            "priority": 90,
            "keywords": [
                "abogado",
                "legal",
                "tribunal",
                "juzgado",
                "causa",
                "audiencia",
                "demanda",
                "contrato",
            ],
            "senders": [],
        },
        {
            "id": "arriendo",
            "label": "arriendo/departamento",
            "priority": 80,
            "keywords": [
                "arriendo",
                "arrendador",
                "departamento",
                "edificio",
                "gasto comun",
                "gasto común",
                "contrato de arriendo",
            ],
            "senders": [],
        },
    ],
    "ignore_senders": [],
    "ignore_keywords": [
        "promocion",
        "promoción",
        "newsletter",
        "oferta",
        "descuento",
        "cyber",
    ],
}


def load_credentials(credentials_file: Path, token_file: Path) -> Credentials:
    creds: Optional[Credentials] = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def gmail_service(credentials_file: Path, token_file: Path):
    return build("gmail", "v1", credentials=load_credentials(credentials_file, token_file))


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def decode_mime_header(value: str) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def header_value(headers: List[Dict[str, str]], name: str) -> str:
    for item in headers:
        if item.get("name", "").lower() == name.lower():
            return decode_mime_header(item.get("value", ""))
    return ""


def decode_body(data: str) -> str:
    if not data:
        return ""
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="ignore")
    except Exception:
        return ""
    raw = re.sub(r"<(br|p|div)[^>]*>", "\n", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(raw)


def walk_parts(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    parts: List[Dict[str, Any]] = []
    stack = [payload]
    while stack:
        item = stack.pop()
        children = item.get("parts") or []
        if children:
            stack.extend(children)
        else:
            parts.append(item)
    return parts


def message_text(payload: Dict[str, Any]) -> str:
    texts: List[str] = []
    for part in walk_parts(payload):
        mime = part.get("mimeType", "")
        if mime not in {"text/plain", "text/html"}:
            continue
        body = part.get("body") or {}
        texts.append(decode_body(body.get("data", "")))
    if not texts:
        texts.append(decode_body((payload.get("body") or {}).get("data", "")))
    text = re.sub(r"\s+", " ", " ".join(texts)).strip()
    return text[:1200]


def normalize(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^a-z0-9áéíóúñü@._+-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def sender_email(from_header: str) -> str:
    match = re.search(r"<([^>]+)>", from_header)
    raw = match.group(1) if match else from_header
    match = re.search(r"[\w.+-]+@[\w.-]+", raw)
    return (match.group(0) if match else raw).lower().strip()


def classify(mail: Dict[str, str], rules: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sender = sender_email(mail["from"])
    text = normalize(" ".join([mail["subject"], mail["snippet"], mail["body"]]))
    for ignored in rules.get("ignore_senders", []):
        if normalize(str(ignored)) in sender:
            return None
    for ignored in rules.get("ignore_keywords", []):
        if normalize(str(ignored)) in text:
            return None

    matches: List[Dict[str, Any]] = []
    for category in rules.get("categories", []):
        reasons: List[str] = []
        for item in category.get("senders", []):
            if normalize(str(item)) in sender:
                reasons.append(f"sender:{item}")
        for item in category.get("keywords", []):
            keyword = normalize(str(item))
            if keyword and keyword in text:
                reasons.append(f"keyword:{item}")
        if reasons:
            matches.append(
                {
                    "id": category.get("id") or "custom",
                    "label": category.get("label") or category.get("id") or "importante",
                    "priority": int(category.get("priority") or 0),
                    "reasons": reasons[:4],
                }
            )
    if not matches:
        return None
    matches.sort(key=lambda item: item["priority"], reverse=True)
    return matches[0]


def fetch_messages(service, query: str, max_results: int) -> List[Dict[str, Any]]:
    response = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    stubs = response.get("messages", [])
    messages: List[Dict[str, Any]] = []
    for stub in stubs:
        msg = service.users().messages().get(userId="me", id=stub["id"], format="full").execute()
        payload = msg.get("payload") or {}
        headers = payload.get("headers") or []
        messages.append(
            {
                "id": msg["id"],
                "thread_id": msg.get("threadId", ""),
                "from": header_value(headers, "From"),
                "subject": header_value(headers, "Subject"),
                "date": header_value(headers, "Date"),
                "snippet": msg.get("snippet", ""),
                "body": message_text(payload),
            }
        )
    return messages


def format_alert(mail: Dict[str, str], classification: Dict[str, Any]) -> str:
    snippet = mail.get("snippet") or mail.get("body") or ""
    snippet = re.sub(r"\s+", " ", snippet).strip()[:280]
    reasons = ", ".join(classification.get("reasons") or [])
    return "\n".join(
        [
            f"📩 Gmail alerta: {classification['label']}",
            f"De: {mail['from']}",
            f"Asunto: {mail['subject'] or '(sin asunto)'}",
            f"Fecha: {mail['date'] or 'sin fecha'}",
            f"Motivo: {reasons}",
            f"Resumen: {snippet}",
        ]
    )


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor Gmail y alerta por WhatsApp.")
    parser.add_argument("--credentials", default="secrets/gmail_credentials.json")
    parser.add_argument("--token", default="secrets/gmail_token.json")
    parser.add_argument("--rules", default="data/gmail_watch_rules.json")
    parser.add_argument("--state", default="data/gmail_watch_state.json")
    parser.add_argument("--outbox", default="data/gmail_alerts_outbox.jsonl")
    parser.add_argument("--target-file", default="secrets/whatsapp_allow_from.txt")
    parser.add_argument("--query", default='is:unread newer_than:30d -category:promotions')
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rules = load_json(ROOT / args.rules, DEFAULT_RULES)
    state_path = ROOT / args.state
    state = load_json(state_path, {"seen": {}, "last_run": None})
    seen: Dict[str, Any] = state.setdefault("seen", {})

    service = gmail_service(ROOT / args.credentials, ROOT / args.token)
    alerts: List[Dict[str, Any]] = []
    scanned = 0
    for mail in fetch_messages(service, args.query, args.max_results):
        scanned += 1
        msg_id = mail["id"]
        if msg_id in seen:
            continue
        classification = classify(mail, rules)
        seen[msg_id] = {
            "seen_at": datetime.now().isoformat(timespec="seconds"),
            "alerted": bool(classification),
            "subject": mail["subject"],
        }
        if not classification:
            continue
        message = format_alert(mail, classification)
        send_result = send_whatsapp(message, ROOT / args.target_file, dry_run=args.dry_run)
        alert = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "message_id": msg_id,
            "thread_id": mail["thread_id"],
            "classification": classification,
            "from": mail["from"],
            "subject": mail["subject"],
            "whatsapp": send_result,
            "message": message,
        }
        alerts.append(alert)
        if not send_result.get("ok"):
            append_jsonl(ROOT / args.outbox, alert)

    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    state["seen"] = dict(list(seen.items())[-5000:])
    save_json(state_path, state)
    result = {
        "status": "ok",
        "scanned": scanned,
        "alerts": len(alerts),
        "outbox": str(ROOT / args.outbox),
        "alert_samples": alerts[:5],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Scanned: {scanned} | alerts: {len(alerts)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
