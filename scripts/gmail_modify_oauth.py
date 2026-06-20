"""OAuth Gmail modify (etiquetas, organizar bandeja)."""
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

import requests

os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from google_auth_oauthlib.flow import Flow

from runtime_paths import secrets_dir
from vida_common import secret_path, writable_secret_path

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.readonly",
]
REDIRECT = "http://localhost:44565/"
PENDING = secrets_dir() / "gmail_modify_oauth_pending.json"


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def resolve_creds() -> Path:
    p = secret_path("gmail_credentials.json")
    if not p:
        raise FileNotFoundError("No se encontró gmail_credentials.json")
    return p


def load_client_config(creds_path: Path) -> dict:
    data = json.loads(creds_path.read_text(encoding="utf-8"))
    return data.get("installed") or data.get("web") or data


def code_from_callback(callback_url: str) -> str:
    code = urllib.parse.parse_qs(urllib.parse.urlparse(callback_url).query).get("code", [""])[0]
    if not code:
        raise ValueError("callback_url sin parametro code")
    return code


def exchange_code_pkce(*, creds_path: Path, redirect_uri: str, code: str, verifier: str) -> dict:
    client = load_client_config(creds_path)
    resp = requests.post(
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
    if resp.status_code >= 400:
        raise RuntimeError(f"Token exchange failed: {resp.status_code} {resp.text}")
    token_data = resp.json()
    expiry = datetime.now(timezone.utc) + timedelta(seconds=int(token_data.get("expires_in", 3600)))
    return {
        "token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "scopes": token_data.get("scope", " ").split() or SCOPES,
        "universe_domain": "googleapis.com",
        "account": "",
        "expiry": expiry.isoformat(),
    }


def cmd_auth_url() -> dict:
    verifier, challenge = pkce_pair()
    creds_path = resolve_creds()
    flow = Flow.from_client_secrets_file(str(creds_path), scopes=SCOPES, redirect_uri=REDIRECT)
    flow.oauth2session.code_verifier = verifier
    url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    token_path = writable_secret_path("gmail_modify_token.json")
    PENDING.parent.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(
        json.dumps(
            {
                "state": state,
                "redirect_uri": REDIRECT,
                "code_verifier": verifier,
                "code_challenge": challenge,
                "credentials": str(creds_path),
                "token": str(token_path),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "status": "needs_auth",
        "auth_url": url,
        "pending": str(PENDING),
        "instruction": "Abre auth_url, autoriza, pega callback con: exchange --callback-url",
    }


def cmd_exchange(callback_url: str) -> dict:
    pending = json.loads(PENDING.read_text(encoding="utf-8"))
    creds_path = Path(pending["credentials"])
    creds_json = exchange_code_pkce(
        creds_path=creds_path,
        redirect_uri=pending["redirect_uri"],
        code=code_from_callback(callback_url),
        verifier=pending["code_verifier"],
    )
    token_path = Path(pending["token"])
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(creds_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "ok", "token": str(token_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="OAuth Gmail modify.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth-url")
    exchange = sub.add_parser("exchange")
    exchange.add_argument("--callback-url", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = cmd_auth_url() if args.cmd == "auth-url" else cmd_exchange(args.callback_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
