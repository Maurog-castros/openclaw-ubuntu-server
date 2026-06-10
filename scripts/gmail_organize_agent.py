"""Organiza Gmail con etiquetas y prepara candidatos spam para aprobacion."""

from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import re
import sys
from datetime import datetime
from email.header import decode_header, make_header
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from vida_common import secret_path, writable_secret_path


SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
ROOT = Path(__file__).resolve().parent.parent

LABELS = {
    "entrevista_trabajo": "OpenClaw/Trabajo",
    "legal": "OpenClaw/Legal",
    "arriendo": "OpenClaw/Arriendo",
    "finanzas": "OpenClaw/Finanzas",
    "boletas": "OpenClaw/Boletas",
    "ofertas_revisar": "OpenClaw/Ofertas-Revisar",
    "newsletter": "OpenClaw/Newsletter",
}

DEFAULT_CATEGORY_RULES = {
    "finanzas": {
        "keywords": ["santander", "banco", "transferencia", "cartola", "estado de cuenta"],
        "senders": [],
    },
    "boletas": {
        "keywords": ["boleta", "factura", "lider", "recibo", "comprobante"],
        "senders": ["contacto@info.lider.cl"],
    },
    "newsletter": {
        "keywords": ["newsletter", "unsubscribe", "suscripcion", "suscripción"],
        "senders": [],
    },
}

OFFER_KEYWORDS = [
    "oferta",
    "promocion",
    "promoción",
    "descuento",
    "cyber",
    "black friday",
    "liquidacion",
    "liquidación",
    "sale",
    "imperdible",
    "últimas horas",
    "ultimas horas",
]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_credentials(token_file: Path) -> Credentials:
    if not token_file.exists():
        raise FileNotFoundError(
            f"Falta {token_file}. Ejecuta gmail_modify_oauth.py auth-url y luego exchange."
        )
    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json(), encoding="utf-8")
    if not creds.valid:
        raise RuntimeError("Token Gmail modify invalido. Reautoriza con gmail_modify_oauth.py.")
    return creds



def resolve_modify_token(token_arg: str) -> Path:
    if token_arg != "secrets/gmail_modify_token.json":
        return ROOT / token_arg
    found = secret_path("gmail_modify_token.json")
    return found if found else writable_secret_path("gmail_modify_token.json")


def gmail_service(token_file: Path):
    return build("gmail", "v1", credentials=load_credentials(token_file))


def normalize(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^a-z0-9áéíóúñü@._+-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def sender_email(from_header: str) -> str:
    match = re.search(r"<([^>]+)>", from_header)
    raw = match.group(1) if match else from_header
    match = re.search(r"[\w.+-]+@[\w.-]+", raw)
    return (match.group(0) if match else raw).lower().strip()


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
    stack = [payload]
    out: List[Dict[str, Any]] = []
    while stack:
        item = stack.pop()
        if item.get("parts"):
            stack.extend(item.get("parts") or [])
        else:
            out.append(item)
    return out


def message_text(payload: Dict[str, Any]) -> str:
    chunks: List[str] = []
    for part in walk_parts(payload):
        if part.get("mimeType") in {"text/plain", "text/html"}:
            chunks.append(decode_body((part.get("body") or {}).get("data", "")))
    if not chunks:
        chunks.append(decode_body((payload.get("body") or {}).get("data", "")))
    return re.sub(r"\s+", " ", " ".join(chunks)).strip()[:2000]


def build_rules(watch_rules: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rules = dict(DEFAULT_CATEGORY_RULES)
    for category in watch_rules.get("categories", []):
        category_id = category.get("id")
        if not category_id:
            continue
        rules[category_id] = {
            "keywords": category.get("keywords") or [],
            "senders": category.get("senders") or [],
        }
    return rules


def classify(mail: Dict[str, str], rules: Dict[str, Dict[str, Any]]) -> tuple[list[str], list[str]]:
    sender = sender_email(mail["from"])
    text = normalize(" ".join([mail["subject"], mail["snippet"], mail["body"]]))
    labels: list[str] = []
    reasons: list[str] = []
    for category_id, rule in rules.items():
        matched = False
        for item in rule.get("senders", []):
            if normalize(str(item)) in sender:
                matched = True
                reasons.append(f"{category_id}:sender:{item}")
        for item in rule.get("keywords", []):
            key = normalize(str(item))
            if key and key in text:
                matched = True
                reasons.append(f"{category_id}:keyword:{item}")
        if matched and category_id in LABELS:
            labels.append(LABELS[category_id])
    if is_unknown_offer(mail, rules):
        labels.append(LABELS["ofertas_revisar"])
        reasons.append("oferta_desconocida:requiere_aprobacion")
    return sorted(set(labels)), reasons[:8]


def is_unknown_offer(mail: Dict[str, str], rules: Dict[str, Dict[str, Any]]) -> bool:
    sender = sender_email(mail["from"])
    text = normalize(" ".join([mail["subject"], mail["snippet"], mail["body"]]))
    if not any(normalize(word) in text for word in OFFER_KEYWORDS):
        return False
    for rule in rules.values():
        for item in rule.get("senders", []):
            if normalize(str(item)) in sender:
                return False
    return True


def fetch_messages(service, query: str, max_results: int) -> List[Dict[str, str]]:
    response = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages: List[Dict[str, str]] = []
    for stub in response.get("messages", []):
        msg = service.users().messages().get(userId="me", id=stub["id"], format="full").execute()
        payload = msg.get("payload") or {}
        headers = payload.get("headers") or []
        messages.append(
            {
                "id": msg["id"],
                "thread_id": msg.get("threadId", ""),
                "label_ids": ",".join(msg.get("labelIds") or []),
                "from": header_value(headers, "From"),
                "subject": header_value(headers, "Subject"),
                "date": header_value(headers, "Date"),
                "snippet": msg.get("snippet", ""),
                "body": message_text(payload),
            }
        )
    return messages


def ensure_labels(service, names: List[str]) -> Dict[str, str]:
    existing = service.users().labels().list(userId="me").execute().get("labels", [])
    by_name = {item["name"]: item["id"] for item in existing}
    for name in names:
        if name in by_name:
            continue
        created = (
            service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )
        by_name[name] = created["id"]
    return by_name


def append_candidates(path: Path, candidates: List[Dict[str, Any]]) -> None:
    existing = load_json(path, {"candidates": []})
    by_id = {item.get("message_id"): item for item in existing.get("candidates", [])}
    for item in candidates:
        by_id[item["message_id"]] = item
    save_json(path, {"candidates": list(by_id.values())[-500:]})


def apply_labels(service, message_id: str, label_ids: List[str]) -> None:
    if not label_ids:
        return
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": label_ids},
    ).execute()


def move_message_to_spam(service, message_id: str) -> None:
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]},
    ).execute()


def cmd_scan(args: argparse.Namespace) -> Dict[str, Any]:
    service = gmail_service(Path(args.token))
    watch_rules = load_json(ROOT / args.watch_rules, {"categories": []})
    rules = build_rules(watch_rules)
    messages = fetch_messages(service, args.query, args.max_results)
    label_names = sorted(set(LABELS.values()))
    label_ids = ensure_labels(service, label_names) if args.apply else {}

    labeled = 0
    candidates: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    for mail in messages:
        labels, reasons = classify(mail, rules)
        if not labels:
            continue
        if args.apply:
            apply_labels(service, mail["id"], [label_ids[name] for name in labels if name in label_ids])
        labeled += 1
        item = {
            "message_id": mail["id"],
            "thread_id": mail["thread_id"],
            "from": mail["from"],
            "subject": mail["subject"],
            "date": mail["date"],
            "labels": labels,
            "reasons": reasons,
        }
        results.append(item)
        if LABELS["ofertas_revisar"] in labels:
            candidates.append(
                {
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "message_id": mail["id"],
                    "thread_id": mail["thread_id"],
                    "sender": sender_email(mail["from"]),
                    "from": mail["from"],
                    "subject": mail["subject"],
                    "date": mail["date"],
                    "status": "pending_approval",
                    "reason": "oferta_desconocida",
                }
            )
    if candidates:
        append_candidates(ROOT / args.spam_candidates, candidates)

    return {
        "status": "ok",
        "mode": "apply" if args.apply else "dry_run",
        "scanned": len(messages),
        "labeled": labeled,
        "spam_candidates": len(candidates),
        "results": results[:30],
        "summary": f"Revisados {len(messages)}; etiquetados {labeled}; spam candidatos {len(candidates)}.",
    }


def cmd_candidates(args: argparse.Namespace) -> Dict[str, Any]:
    data = load_json(ROOT / args.spam_candidates, {"candidates": []})
    pending = [item for item in data.get("candidates", []) if item.get("status") == "pending_approval"]
    return {"status": "ok", "pending_count": len(pending), "pending": pending[:50]}


def cmd_approve_spam(args: argparse.Namespace) -> Dict[str, Any]:
    service = gmail_service(Path(args.token))
    data = load_json(ROOT / args.spam_candidates, {"candidates": []})
    approved = 0
    for item in data.get("candidates", []):
        if item.get("status") != "pending_approval":
            continue
        sender_match = args.sender and args.sender.lower() in str(item.get("sender", "")).lower()
        id_match = args.message_id and args.message_id == item.get("message_id")
        if not sender_match and not id_match:
            continue
        if args.apply:
            move_message_to_spam(service, item["message_id"])
        item["status"] = "approved_spam" if args.apply else "would_approve_spam"
        item["approved_at"] = datetime.now().isoformat(timespec="seconds")
        approved += 1
    if args.apply:
        save_json(ROOT / args.spam_candidates, data)
    return {
        "status": "ok",
        "mode": "apply" if args.apply else "dry_run",
        "approved": approved,
        "summary": f"Spam aprobados: {approved} ({'aplicado' if args.apply else 'simulado'}).",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Organiza Gmail.")
    parser.add_argument("--token", default="secrets/gmail_modify_token.json")
    parser.add_argument("--watch-rules", default="data/gmail_watch_rules.json")
    parser.add_argument("--spam-candidates", default="data/gmail_spam_candidates.json")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan")
    scan.add_argument("--query", default="in:inbox newer_than:365d")
    scan.add_argument("--max-results", type=int, default=300)
    scan.add_argument("--apply", action="store_true")

    sub.add_parser("candidates")

    approve = sub.add_parser("approve-spam")
    approve.add_argument("--sender", default="")
    approve.add_argument("--message-id", default="")
    approve.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    args.token = str(resolve_modify_token(args.token))

    try:
        if args.cmd == "scan":
            result = cmd_scan(args)
        elif args.cmd == "candidates":
            result = cmd_candidates(args)
        else:
            result = cmd_approve_spam(args)
    except (FileNotFoundError, RuntimeError) as exc:
        result = {
            "status": "needs_auth",
            "error": str(exc),
            "next": "Ejecuta: gmail_modify_oauth.py --json auth-url",
        }
    except HttpError as exc:
        result = {"status": "error", "error": str(exc)}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("summary") or result)
    if result.get("status") in {"error", "needs_auth"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
