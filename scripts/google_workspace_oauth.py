#!/usr/bin/env python3
"""OAuth unificado para Gmail, Calendar, Google Sheets y Drive."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from runtime_paths import secrets_dir
from vida_common import ROOT, secret_path

os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
REDIRECT_URI = "http://localhost:44567/"
SECRETS_DIR = secrets_dir()
TOKEN_PATH = SECRETS_DIR / "google_workspace_token.json"
PENDING_PATH = SECRETS_DIR / "google_workspace_oauth_pending.json"


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def resolve_client_credentials() -> Path:
    path = secret_path("gmail_credentials.json")
    if not path:
        raise FileNotFoundError("No se encontro gmail_credentials.json en secrets.")
    return path


def load_client_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    config = data.get("installed") or data.get("web") or data
    if not config.get("client_id") or not config.get("client_secret"):
        raise ValueError("gmail_credentials.json no contiene client_id/client_secret.")
    return config


def callback_parameters(callback_url: str) -> dict[str, str]:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(callback_url).query)
    if query.get("error"):
        raise PermissionError(f"Google OAuth rechazo la autorizacion: {query['error'][0]}")
    code = query.get("code", [""])[0]
    state = query.get("state", [""])[0]
    if not code:
        raise ValueError("callback_url sin parametro code.")
    return {"code": code, "state": state}


def write_secret_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def exchange_code(
    *,
    credentials_path: Path,
    redirect_uri: str,
    code: str,
    verifier: str,
) -> dict[str, Any]:
    client = load_client_config(credentials_path)
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        },
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Google token exchange fallo HTTP {response.status_code}.")
    token = response.json()
    expiry = datetime.now(timezone.utc) + timedelta(
        seconds=int(token.get("expires_in", 3600))
    )
    granted_scopes = token.get("scope", " ").split() or SCOPES
    missing = sorted(set(SCOPES) - set(granted_scopes))
    if missing:
        raise PermissionError(f"Google no concedio todos los scopes: {missing}")
    return {
        "token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "scopes": granted_scopes,
        "universe_domain": "googleapis.com",
        "account": "",
        "expiry": expiry.isoformat(),
    }


def cmd_auth_url() -> dict[str, Any]:
    verifier, challenge = pkce_pair()
    credentials_path = resolve_client_credentials()
    flow = Flow.from_client_secrets_file(
        str(credentials_path),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    flow.oauth2session.code_verifier = verifier
    url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    write_secret_json(
        PENDING_PATH,
        {
            "state": state,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
            "credentials": str(credentials_path),
            "token": str(TOKEN_PATH),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {
        "status": "needs_auth",
        "auth_url": url,
        "pending": str(PENDING_PATH),
        "token": str(TOKEN_PATH),
        "instruction": (
            "Abre auth_url, autoriza y copia la URL localhost final. "
            "Luego ejecuta exchange --callback-url '<URL>'."
        ),
    }


def cmd_exchange(callback_url: str) -> dict[str, Any]:
    if not PENDING_PATH.exists():
        raise FileNotFoundError("No hay OAuth pendiente. Ejecuta auth-url primero.")
    pending = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    callback = callback_parameters(callback_url)
    if callback["state"] != pending["state"]:
        raise PermissionError("OAuth state invalido; reinicia con auth-url.")
    credentials_json = exchange_code(
        credentials_path=Path(pending["credentials"]),
        redirect_uri=pending["redirect_uri"],
        code=callback["code"],
        verifier=pending["code_verifier"],
    )
    token_path = Path(pending["token"])
    write_secret_json(token_path, credentials_json)
    PENDING_PATH.unlink(missing_ok=True)
    return {
        "status": "ok",
        "token": str(token_path),
        "scope_count": len(credentials_json["scopes"]),
        "instruction": "Valida con: google_workspace_oauth.py check",
    }


def api_check(url: str, credentials: Credentials) -> None:
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {credentials.token}"},
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Validacion Google fallo HTTP {response.status_code}: {url}")


def cmd_check(spreadsheet_id: str = "") -> dict[str, Any]:
    if not TOKEN_PATH.exists():
        raise FileNotFoundError(f"No existe token: {TOKEN_PATH}")
    credentials = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        write_secret_json(TOKEN_PATH, json.loads(credentials.to_json()))
    if not credentials.valid or not credentials.has_scopes(SCOPES):
        raise PermissionError("Token Google Workspace invalido o sin scopes completos.")
    api_check("https://gmail.googleapis.com/gmail/v1/users/me/profile", credentials)
    api_check(
        "https://www.googleapis.com/calendar/v3/users/me/calendarList?maxResults=1",
        credentials,
    )
    checked = ["gmail", "calendar"]
    if spreadsheet_id:
        fields = urllib.parse.quote("spreadsheetId,properties.title", safe=",")
        api_check(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}?fields={fields}",
            credentials,
        )
        checked.append("sheets")
    return {
        "status": "ok",
        "token": str(TOKEN_PATH),
        "checked": checked,
        "scope_count": len(SCOPES),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("auth-url")
    exchange = subparsers.add_parser("exchange")
    exchange.add_argument("--callback-url", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--spreadsheet-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "auth-url":
        result = cmd_auth_url()
    elif args.command == "exchange":
        result = cmd_exchange(args.callback_url)
    else:
        result = cmd_check(args.spreadsheet_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
