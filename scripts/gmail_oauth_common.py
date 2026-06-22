"""Gmail OAuth: carga unificada, sync desde workspace token y salud."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from runtime_paths import secrets_dir

GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_MODIFY = "https://www.googleapis.com/auth/gmail.modify"
WORKSPACE_TOKEN = "google_workspace_token.json"

LEGACY_SYNC_TARGETS: tuple[tuple[str, list[str]], ...] = (
    ("gmail_token.json", [GMAIL_READONLY]),
    ("gmail_modify_token.json", [GMAIL_MODIFY, GMAIL_READONLY]),
)


def token_file(name: str) -> Path:
    return secrets_dir() / name


def backup_token(path: Path, *, reason: str = "backup") -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak-{reason}-{stamp}")
    shutil.copy2(path, backup)
    backup.chmod(0o600)
    return backup


def write_token_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _load_and_refresh(path: Path, scopes: list[str]) -> Credentials:
    creds = Credentials.from_authorized_user_file(str(path), scopes)
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        write_token_json(path, json.loads(creds.to_json()))
        return creds
    raise RefreshError("Token Gmail expirado sin refresh valido.")


def _workspace_source_data() -> dict[str, Any] | None:
    path = token_file(WORKSPACE_TOKEN)
    if not path.exists():
        return None
    try:
        creds = _load_and_refresh(path, [GMAIL_MODIFY, GMAIL_READONLY])
        if not creds.valid or not creds.refresh_token:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def sync_legacy_tokens_from_workspace(*, force: bool = False) -> bool:
    """Propaga el refresh_token del workspace token a gmail_*.json legacy."""
    source = _workspace_source_data()
    if not source:
        return False

    changed = False
    for name, scopes in LEGACY_SYNC_TARGETS:
        destination = token_file(name)
        if destination.exists() and not force:
            try:
                _load_and_refresh(destination, scopes)
                continue
            except Exception:
                pass
        backup_token(destination, reason="sync")
        payload = dict(source)
        payload["scopes"] = scopes
        write_token_json(destination, payload)
        changed = True
    return changed


def load_gmail_credentials(
    scopes: list[str] | None = None,
    *,
    preferred: Path | None = None,
    allow_sync: bool = True,
) -> tuple[Credentials, Path]:
    """Carga credenciales Gmail; re-sincroniza legacy si el refresh falla."""
    required = scopes or [GMAIL_READONLY]
    candidates: list[Path] = []
    if preferred and preferred.exists():
        candidates.append(preferred)
    for name in (WORKSPACE_TOKEN, "gmail_modify_token.json", "gmail_token.json"):
        path = token_file(name)
        if path not in candidates:
            candidates.append(path)

    last_error: Exception | None = None
    for path in candidates:
        if not path.exists():
            continue
        try:
            creds = _load_and_refresh(path, required)
            if creds.valid and creds.has_scopes(required):
                return creds, path
        except Exception as exc:
            last_error = exc

    if allow_sync and sync_legacy_tokens_from_workspace():
        return load_gmail_credentials(required, preferred=preferred, allow_sync=False)

    hint = "Reautoriza: google_workspace_oauth.py auth-url && exchange --callback-url"
    if last_error:
        raise RuntimeError(f"Gmail OAuth invalido. {hint}") from last_error
    raise FileNotFoundError(f"No hay token Gmail. {hint}")


def probe_token(path: Path, scopes: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "status": "missing", "valid": False}
    try:
        creds = _load_and_refresh(path, scopes)
        return {
            "path": str(path),
            "status": "ok",
            "valid": creds.valid,
            "has_refresh": bool(creds.refresh_token),
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }
    except Exception as exc:
        return {
            "path": str(path),
            "status": "error",
            "valid": False,
            "error": str(exc)[:200],
        }


def check_gmail_oauth_health() -> dict[str, Any]:
    probes = [
        probe_token(token_file(WORKSPACE_TOKEN), [GMAIL_MODIFY, GMAIL_READONLY]),
        probe_token(token_file("gmail_modify_token.json"), [GMAIL_MODIFY, GMAIL_READONLY]),
        probe_token(token_file("gmail_token.json"), [GMAIL_READONLY]),
    ]
    workspace_ok = probes[0]["status"] == "ok"
    legacy_ok = any(p["status"] == "ok" for p in probes[1:])
    synced = False
    if workspace_ok and not legacy_ok:
        synced = sync_legacy_tokens_from_workspace()
        if synced:
            probes[1:] = [
                probe_token(token_file("gmail_modify_token.json"), [GMAIL_MODIFY, GMAIL_READONLY]),
                probe_token(token_file("gmail_token.json"), [GMAIL_READONLY]),
            ]
            legacy_ok = any(p["status"] == "ok" for p in probes[1:])
    healthy = workspace_ok and legacy_ok
    return {
        "status": "ok" if healthy else "needs_auth",
        "healthy": healthy,
        "workspace_ok": workspace_ok,
        "legacy_ok": legacy_ok,
        "synced": synced,
        "tokens": probes,
        "reauth": "google_workspace_oauth.py auth-url",
    }
