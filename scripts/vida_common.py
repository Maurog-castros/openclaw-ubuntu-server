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


LEAKED_TOOL_LINE_RE = re.compile(
    r"^\s*(?:memory_search|memory_get|read|write|exec|message|web_search|browser)\s*\(",
    re.I,
)
LEAKED_TOOL_ONLY_RE = re.compile(
    r"^\s*(?:memory_search|memory_get|read|write|exec|message|web_search|browser)"
    r"\s*\([^)]*\)\s*\.?\s*$",
    re.I | re.S,
)


def is_leaked_tool_call(text: str) -> bool:
    """True when the model emitted a tool invocation as user-visible text."""
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if LEAKED_TOOL_ONLY_RE.match(cleaned):
        return True
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    return bool(lines) and all(LEAKED_TOOL_LINE_RE.match(ln) for ln in lines)


def strip_leaked_tool_calls(text: str) -> str:
    if not text or is_leaked_tool_call(text):
        return ""
    kept: list[str] = []
    for line in text.splitlines():
        if LEAKED_TOOL_LINE_RE.match(line.strip()):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def truncate_whatsapp(text: str, max_len: int = 500) -> str:
    """Un mensaje WhatsApp; sin bloques largos ni citas pegadas."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[: max_len + 1].rsplit(" ", 1)[0]
    if not cut or len(cut) < max_len // 2:
        cut = cleaned[:max_len]
    return cut.rstrip(".,;:- ") + "…"
