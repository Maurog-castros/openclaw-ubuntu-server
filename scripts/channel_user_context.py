"""Contexto multi-usuario WhatsApp: datos y estado aislados por teléfono."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent

CONFIG_CANDIDATES = (
    ROOT / "data/whatsapp_users.json",
    ROOT / "config/whatsapp_users.json",
    ROOT / "secrets/whatsapp_users.json",
)

PEER_SESSION_RE = re.compile(r"(?:^|:)whatsapp(?::[^:\s]+)*:(\+\d{8,15})(?:$|[:\s])", re.I)
ALL_AGENTS = frozenset({"fin", "care", "broh", "supp", "intel", "jobs", "hlgo", "content"})


@dataclass(frozen=True)
class ChannelUserContext:
    user_id: str
    display_name: str
    peer_e164: str
    is_owner: bool
    data_root: Path
    care_data: Path
    sticky_file: Path
    menu_file: Path
    inbound_dir: Path
    allowed_agents: FrozenSet[str]

    def allows(self, agent: str) -> bool:
        return agent in self.allowed_agents


def normalize_phone(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("telegram:"):
        return raw.lower()
    if raw.startswith("+"):
        digits = re.sub(r"\D", "", raw)
        return f"+{digits}" if digits else ""
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if digits.startswith("56"):
        return f"+{digits}"
    if len(digits) == 9 and digits[0] == "9":
        return f"+56{digits}"
    return f"+{digits}"


def peer_from_session_key(session_key: str) -> str:
    match = PEER_SESSION_RE.search(session_key or "")
    if match:
        return normalize_phone(match.group(1))
    fallback = re.search(r"\+\d{8,15}", session_key or "")
    return normalize_phone(fallback.group(0)) if fallback else ""


def _load_config() -> dict:
    for path in CONFIG_CANDIDATES:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
    return {}


def _resolve_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return ROOT / value


def _build_context(tenant_id: str, spec: dict, phone: str) -> ChannelUserContext:
    data_root = _resolve_path(str(spec.get("data_root") or f"data/users/{tenant_id}"))
    care_data = _resolve_path(str(spec.get("care_data") or data_root / "care"))
    allowed = frozenset(spec.get("allowed_agents") or ALL_AGENTS)
    sticky = data_root / "whatsapp_last_agent.json"
    menu = data_root / "whatsapp_last_menu.json"
    inbound = ROOT / "data/config/media/inbound" / tenant_id
    return ChannelUserContext(
        user_id=tenant_id,
        display_name=str(spec.get("name") or tenant_id),
        peer_e164=phone,
        is_owner=bool(spec.get("is_owner")),
        data_root=data_root,
        care_data=care_data,
        sticky_file=sticky,
        menu_file=menu,
        inbound_dir=inbound,
        allowed_agents=allowed,
    )


def _match_tenant(phone: str, tenants: dict) -> tuple[str, dict] | None:
    if not phone:
        return None
    for tenant_id, spec in tenants.items():
        phones = {normalize_phone(item) for item in (spec.get("phones") or [])}
        telegram_ids = {normalize_phone(item) for item in (spec.get("telegram_ids") or [])}
        if phone in phones or phone in telegram_ids:
            return tenant_id, spec
    return None


def _guest_context_spec(phone: str, session_key: str) -> tuple[str, dict]:
    digits = re.sub(r"[^0-9]", "", phone)
    if digits:
        suffix = digits[-8:]
    else:
        seed = (session_key or "unknown-whatsapp-peer").encode("utf-8")
        suffix = hashlib.sha256(seed).hexdigest()[:10]
    guest_id = f"guest_{suffix}"
    return guest_id, {
        "name": "Invitado",
        "is_owner": False,
        "data_root": f"data/users/{guest_id}",
        "care_data": f"data/users/{guest_id}/care",
        "allowed_agents": ["fin", "care"],
    }


def resolve_user_context(*, peer: str = "", session_key: str = "") -> ChannelUserContext:
    phone = normalize_phone(peer) or peer_from_session_key(session_key)
    tenants = (_load_config().get("tenants") or {})

    matched = _match_tenant(phone, tenants)
    if matched:
        tenant_id, spec = matched
        return _build_context(tenant_id, spec, phone)

    guest_id, guest_spec = _guest_context_spec(phone, session_key)
    return _build_context(guest_id, guest_spec, phone)


def ensure_user_dirs(ctx: ChannelUserContext) -> None:
    ctx.data_root.mkdir(parents=True, exist_ok=True)
    ctx.care_data.mkdir(parents=True, exist_ok=True)
    ctx.inbound_dir.mkdir(parents=True, exist_ok=True)
    ctx.sticky_file.parent.mkdir(parents=True, exist_ok=True)
    if ctx.is_owner:
        return
    import sys

    scr = ROOT / "scripts"
    if str(scr) not in sys.path:
        sys.path.insert(0, str(scr))
    from finanzas_common import DEFAULT_UNIFIED_CSV, UNIFIED_COLUMNS, ensure_csv_headers

    unified = ctx.data_root / DEFAULT_UNIFIED_CSV.replace("data/", "", 1)
    ensure_csv_headers(unified, UNIFIED_COLUMNS)
    profile = ctx.care_data / "profile.json"
    if not profile.exists():
        profile.write_text(
            json.dumps({"name": ctx.display_name}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def apply_user_env(ctx: ChannelUserContext) -> None:
    ensure_user_dirs(ctx)
    os.environ["OPENCLAW_USER_DATA_ROOT"] = str(ctx.data_root)
    os.environ["OPENCLAW_USER_CARE_DATA"] = str(ctx.care_data)
    os.environ["OPENCLAW_USER_STICKY_FILE"] = str(ctx.sticky_file)
    os.environ["OPENCLAW_USER_MENU_FILE"] = str(ctx.menu_file)
    os.environ["OPENCLAW_USER_INBOUND_DIR"] = str(ctx.inbound_dir)
    os.environ["OPENCLAW_USER_ID"] = ctx.user_id
    os.environ["OPENCLAW_USER_PEER"] = ctx.peer_e164
    os.environ["OPENCLAW_USER_IS_OWNER"] = "1" if ctx.is_owner else "0"
    os.environ["OPENCLAW_USER_NAME"] = ctx.display_name


def current_user_context() -> ChannelUserContext | None:
    user_id = os.environ.get("OPENCLAW_USER_ID", "").strip()
    if not user_id:
        return None
    return resolve_user_context(
        peer=os.environ.get("OPENCLAW_USER_PEER", ""),
        session_key="",
    )


def guest_agent_denied_message(agent: str) -> str:
    labels = {
        "supp": "soporte técnico del servidor",
        "intel": "radar de inteligencia",
        "jobs": "postulaciones",
        "hlgo": "HL-Go",
        "broh": "compañero Broh",
        "content": "contenido Instagram",
    }
    label = labels.get(agent, agent)
    return (
        f"*{label}* no está disponible en tu espacio personal.\n"
        "Puedes usar:\n"
        "• /fin — gastos, saldo, boletas\n"
        "• /care — diario, ánimo, salud\n"
        "• /help — ayuda\n"
        "• /new — reiniciar conversación"
    )
