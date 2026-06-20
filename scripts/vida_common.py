"""Utilidades compartidas agente care."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from runtime_paths import repo_root, secrets_dir

ROOT = repo_root()
WS = ROOT / "data/workspace/care"
TZ = ZoneInfo("America/Santiago")


def care_data() -> Path:
    override = os.environ.get("OPENCLAW_USER_CARE_DATA", "").strip()
    if override:
        return Path(override)
    return WS / "data"

SECRET_DIRS = [
    secrets_dir(),
    Path("/home/node/.openclaw-secrets"),
]


def secret_path(name: str) -> Path | None:
    for base in SECRET_DIRS:
        candidate = base / name
        if candidate.exists():
            return candidate
    return None


def writable_secret_path(name: str) -> Path:
    target = secrets_dir() / name
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def now_local() -> datetime:
    return datetime.now(TZ)


def load_json(path: Path, default: dict) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def reply(text: str, **extra) -> dict:
    payload = {"status": "ok", "whatsapp_reply": truncate_whatsapp(text)}
    payload.update(extra)
    return payload


def truncate_whatsapp(text: str, max_len: int = 500) -> str:
    """Un mensaje WhatsApp; sin bloques largos ni citas pegadas."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[: max_len + 1].rsplit(" ", 1)[0]
    if not cut or len(cut) < max_len // 2:
        cut = cleaned[:max_len]
    return cut.rstrip(".,;:- ") + "…"
