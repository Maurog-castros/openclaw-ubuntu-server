"""Lee codigo MFA Laborum desde Gmail (no_reply@laborum.cl)."""

from __future__ import annotations

import base64
import re
import time
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

from jobs_common import ROOT

GMAIL_QUERY = 'from:no_reply@laborum.cl subject:acceso newer_than:30m'
SUBJECT_CODE_RE = re.compile(r"c[oó]digo de acceso es:\s*(\d{6})", re.I)
BODY_CODE_RE = re.compile(r"\b(\d{6})\b")

DEFAULT_CREDENTIALS = ROOT / "secrets/gmail_credentials.json"
TOKEN_CANDIDATES = [
    ROOT / "secrets/gmail_modify_token.json",
    ROOT / "data/secrets/gmail_modify_token.json",
    ROOT / "secrets/gmail_token.json",
    ROOT / "data/secrets/gmail_calendar_token.json",
]


def _resolve_token_file(token_file: Path | None = None) -> Path:
    if token_file and token_file.exists():
        return token_file
    for candidate in TOKEN_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No hay token Gmail (gmail_modify_token.json o gmail_token.json).")


def _load_credentials(credentials_file: Path, token_file: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(f"Token Gmail invalido o ausente: {token_file}")
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _gmail_service(credentials_file: Path | None = None, token_file: Path | None = None):
    from googleapiclient.discovery import build

    creds = credentials_file or DEFAULT_CREDENTIALS
    token = _resolve_token_file(token_file)
    return build("gmail", "v1", credentials=_load_credentials(creds, token))


def _message_text(service: Any, message_id: str) -> tuple[str, str, int]:
    full = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in full.get("payload", {}).get("headers", [])}
    subject = headers.get("subject", "")
    internal_ms = int(full.get("internalDate") or 0)
    chunks: list[str] = [subject]

    def walk(part: dict[str, Any]) -> None:
        body = part.get("body") or {}
        data = body.get("data")
        if data:
            raw = base64.urlsafe_b64decode(data + "==")
            mime = part.get("mimeType", "")
            if mime.startswith("text/") or mime == "message/rfc822":
                chunks.append(raw.decode("utf-8", errors="replace"))
            elif mime == "message/rfc822" or part.get("filename", "").endswith(".eml"):
                msg = BytesParser(policy=policy.default).parsebytes(raw)
                chunks.append(msg.get_content())
        for sub in part.get("parts") or []:
            walk(sub)

    walk(full.get("payload") or {})
    return subject, "\n".join(chunks), internal_ms


def extract_mfa_code(subject: str, body: str = "") -> str | None:
    blob = f"{subject}\n{body}"
    match = SUBJECT_CODE_RE.search(blob)
    if match:
        return match.group(1)
    if "laborum" in blob.lower() or "codigo de acceso" in blob.lower() or "código de acceso" in blob.lower():
        for code in BODY_CODE_RE.findall(blob):
            return code
    return None


def fetch_latest_laborum_mfa_code(
    *,
    not_before_ms: int | None = None,
    credentials_file: Path | None = None,
    token_file: Path | None = None,
) -> str | None:
    service = _gmail_service(credentials_file, token_file)
    response = service.users().messages().list(userId="me", q=GMAIL_QUERY, maxResults=10).execute()
    messages = response.get("messages") or []
    best: tuple[int, str] | None = None
    for item in messages:
        subject, body, internal_ms = _message_text(service, item["id"])
        if not_before_ms and internal_ms < not_before_ms:
            continue
        code = extract_mfa_code(subject, body)
        if not code:
            continue
        if best is None or internal_ms > best[0]:
            best = (internal_ms, code)
    return best[1] if best else None


def wait_for_laborum_mfa_code(
    *,
    not_before_ms: int | None = None,
    wait_sec: int = 120,
    poll_sec: int = 4,
    credentials_file: Path | None = None,
    token_file: Path | None = None,
) -> str:
    deadline = time.time() + wait_sec
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            code = fetch_latest_laborum_mfa_code(
                not_before_ms=not_before_ms,
                credentials_file=credentials_file,
                token_file=token_file,
            )
            if code:
                return code
        except Exception as exc:
            last_error = exc
        time.sleep(poll_sec)
    if last_error:
        raise RuntimeError(f"No llego codigo Laborum por Gmail en {wait_sec}s: {last_error}") from last_error
    raise RuntimeError(f"No llego codigo Laborum por Gmail en {wait_sec}s.")
