"""OAuth y credenciales Google Calendar para agente care."""
from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from vida_common import ROOT, secret_path, writable_secret_path

SCOPES_READ = ["https://www.googleapis.com/auth/calendar.readonly"]
SCOPES_WRITE = ["https://www.googleapis.com/auth/calendar.events"]
SCOPES_ALL = list(dict.fromkeys(SCOPES_WRITE + SCOPES_READ))

TOKEN_NAMES = ["gmail_calendar_token.json", "gmail_token.json"]


def token_candidates() -> list[Path]:
    found: list[Path] = []
    for name in TOKEN_NAMES:
        p = secret_path(name)
        if p:
            found.append(p)
    default = writable_secret_path("gmail_calendar_token.json")
    if default not in found:
        found.append(default)
    return found


def get_creds(*, write: bool = False) -> Credentials | None:
    needed = SCOPES_ALL if write else SCOPES_READ
    for path in token_candidates():
        if not path.exists():
            continue
        creds = Credentials.from_authorized_user_file(str(path), needed)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if path.parent.exists() and os.access(path.parent, os.W_OK):
                path.write_text(creds.to_json(), encoding="utf-8")
        if write and creds.has_scopes(SCOPES_WRITE):
            return creds
        if not write and creds.has_scopes(SCOPES_READ):
            return creds
    return None


def calendar_auth_hint() -> str:
    return (
        "Calendario no autorizado para crear citas.\n"
        "En el servidor ejecuta:\n"
        "docker exec openclaw-openclaw-gateway-1 /home/node/openclaw-mauro/scripts/run-vida-py.sh "
        "/home/node/openclaw-mauro/scripts/vida_calendar_oauth.py auth-url\n"
        "Autoriza en el navegador y completa con exchange --callback-url."
    )
