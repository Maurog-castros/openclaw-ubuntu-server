#!/usr/bin/env python3
"""Registra agente supp en openclaw.json y escribe SOUL."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path("/home/mauro/openclaw-mauro")
CONFIG_PATH = REPO_ROOT / "data/config/openclaw.json"
SOUL_PATH = REPO_ROOT / "data/workspace/support/SOUL.md"
CONTAINER_SCRIPTS = "/home/node/openclaw-mauro/scripts"
CONTAINER_RUN_PY = f"{CONTAINER_SCRIPTS}/run-finanzas-py.sh"

SUPP_SOUL = f"""# Agente Soporte (/supp)

Experto OpenClaw, agentes LLM, gateway Docker, WhatsApp cola, context overflow.
Espanol chileno. Respuestas CORTAS (max 8 lineas). WhatsApp: *negrita*, emojis, ───. Menu 1-5 al final.

## WhatsApp /supp

Siempre primero:
`{CONTAINER_RUN_PY} {CONTAINER_SCRIPTS}/support_delegate.py --text "<msg>" --json`
Copia `whatsapp_reply`. NUNCA NO_REPLY.

Subcomandos usuario: status, scan, fix, ultimos, listar cron jobs.

## Exec permitido

- support_scan_logs.py --json
- support_remediate.py --auto --json
- support_list_crons.py --json (listar cron jobs del host; copia whatsapp_reply, PROHIBIDO inventar crons)
- clear-whatsapp-pending-remote.sh (solo si delegate/fix lo indica)

PROHIBIDO: editar data/finanzas*, secrets, force push.

## Formato respuesta

Supp — [accion]
Encontre: ...
Registro: finding_id en data/support_findings.csv
Hice: ...
Verifique: gateway healthy
Commit: hash o sin cambios

## Background

Cron host cada 5m: support_watch.py (scan+fix+commit+push automatico).
"""

SUPP_AGENT = {
    "id": "supp",
    "name": "supp",
    "description": "Soporte tecnico OpenClaw: logs, remediacion, CSV hallazgos",
    "workspace": "/home/node/.openclaw/workspace/support",
    "agentDir": "/home/node/.openclaw/agents/supp/agent",
    "model": {
        "primary": "remote-lm/openclaw-remote-coder",
        "fallbacks": ["remote-lm/openclaw-remote"],
    },
    "identity": {"name": "Supp", "theme": "soporte tecnico agentes LLM", "emoji": "🛠"},
    "sandbox": {"mode": "off"},
    "tools": {
        "allow": ["read", "exec", "message", "memory_search", "memory_get"],
        "exec": {
            "host": "gateway",
            "security": "full",
            "ask": "off",
            "strictInlineEval": True,
        },
    },
}


def backup(path: Path) -> None:
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_suffix(path.suffix + f".bak-supp-{stamp}"))


def patch_supp_agent(data: dict) -> bool:
    agents = data.setdefault("agents", {}).setdefault("list", [])
    others = [a for a in agents if a.get("id") != "supp"]
    existing = next((a for a in agents if a.get("id") == "supp"), None)
    target = dict(SUPP_AGENT)
    if existing:
        target.update({k: v for k, v in existing.items() if k not in target})
    data["agents"]["list"] = others + [target]
    return True


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"ERROR: no existe {CONFIG_PATH}", file=sys.stderr)
        return 1
    backup(CONFIG_PATH)
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    patch_supp_agent(data)
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    SOUL_PATH.parent.mkdir(parents=True, exist_ok=True)
    backup(SOUL_PATH)
    SOUL_PATH.write_text(SUPP_SOUL, encoding="utf-8")
    (SOUL_PATH.parent / "AGENTS.md").write_text(
        "# Supp — ver scripts/support_*.py y .cursor/skills/openclaw-support-agent/\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "soul": str(SOUL_PATH), "agent": "supp"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
