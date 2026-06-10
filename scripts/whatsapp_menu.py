"""Menu numerado WhatsApp (respuestas 1-5) + persistencia."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parent.parent
DEFAULT_MENU_STATE = _REPO / "data/whatsapp_last_menu.json"

MENU_CHOICE_RE = re.compile(r"^[1-5]$")
EMOJI_NUM = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


@dataclass
class MenuOption:
    key: str
    emoji: str
    label: str
    kind: str  # text | script | monthly | supp
    value: str = ""

    def to_dict(self) -> dict:
        return {"key": self.key, "emoji": self.emoji, "label": self.label, "kind": self.kind, "value": self.value}


def _current_month() -> str:
    return date.today().strftime("%Y-%m")


def fin_menu_options() -> List[MenuOption]:
    month = _current_month()
    return [
        MenuOption("1", "💰", "Ver saldo", "text", "como va mi saldo"),
        MenuOption("2", "💸", "Transferencias recientes", "script", "finanzas_transferencias_report.py|--limit|5"),
        MenuOption("3", "📊", f"Gastos {month}", "monthly", month),
        MenuOption("4", "🧾", "Ultimas boletas", "script", "finanzas_recent_receipts.py|--limit|5"),
        MenuOption("5", "🛠", "Soporte tecnico", "supp", "status"),
    ]


def supp_menu_options() -> List[MenuOption]:
    return [
        MenuOption("1", "🔍", "Escanear logs", "supp", "scan"),
        MenuOption("2", "🔧", "Auto-fix", "supp", "fix"),
        MenuOption("3", "📋", "Estado sistema", "supp", "status"),
        MenuOption("4", "💰", "Volver a finanzas", "text", "como va mi saldo"),
    ]


def load_menu_state(path: Path = DEFAULT_MENU_STATE) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_menu_state(agent: str, options: List[MenuOption], path: Path = DEFAULT_MENU_STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_menu_state(path)
    data["default"] = {
        "agent": agent,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "options": [o.to_dict() for o in options],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_menu_footer(agent: str) -> str:
    options = fin_menu_options() if agent == "fin" else supp_menu_options()
    save_menu_state(agent, options)
    lines = ["", "───", "*Acciones rapidas* (responde el numero):"]
    for i, opt in enumerate(options):
        num = EMOJI_NUM[i] if i < len(EMOJI_NUM) else f"{opt.key}."
        lines.append(f"{num} {opt.label}")
    return "\n".join(lines)


def resolve_menu_choice(text: str, path: Path = DEFAULT_MENU_STATE) -> Optional[MenuOption]:
    t = (text or "").strip()
    if not MENU_CHOICE_RE.match(t):
        return None
    state = load_menu_state(path).get("default") or {}
    for raw in state.get("options") or []:
        if str(raw.get("key")) == t:
            return MenuOption(
                key=str(raw.get("key")),
                emoji=str(raw.get("emoji") or ""),
                label=str(raw.get("label") or ""),
                kind=str(raw.get("kind") or "text"),
                value=str(raw.get("value") or ""),
            )
    return None


def finish_reply(body: str, *, agent: str, skip_menu: bool = False) -> str:
    from whatsapp_format import format_whatsapp_reply

    formatted = format_whatsapp_reply(body or "")
    if skip_menu or not formatted:
        return formatted
    if "*Acciones rapidas*" in formatted:
        return formatted
    return formatted + build_menu_footer(agent)
