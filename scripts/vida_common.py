"""Utilidades compartidas agente care."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent
WS = ROOT / "data/workspace/care"
TZ = ZoneInfo("America/Santiago")


def care_data() -> Path:
    override = os.environ.get("OPENCLAW_USER_CARE_DATA", "").strip()
    if override:
        return Path(override)
    return WS / "data"

SECRET_DIRS = [
    ROOT / "secrets",
    Path("/home/node/.openclaw-secrets"),
    Path("/home/mauro/openclaw-mauro/secrets"),
    ROOT / "data/secrets",
]


def secret_path(name: str) -> Path | None:
    for base in SECRET_DIRS:
        candidate = base / name
        if candidate.exists():
            return candidate
    return None


def writable_secret_path(name: str) -> Path:
    host_dir = Path("/home/mauro/openclaw-mauro/secrets")
    if host_dir.exists():
        try:
            test = host_dir / ".write_test"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
            return host_dir / name
        except OSError:
            pass
    fallback = ROOT / "data/secrets"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback / name


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
