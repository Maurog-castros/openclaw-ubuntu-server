#!/usr/bin/env python3
"""Registra agente broh en openclaw.json y escribe workspace SOUL/AGENTS."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path("/home/mauro/Dev/openclaw-mauro")
if not REPO_ROOT.exists():
    REPO_ROOT = Path(__file__).resolve().parent.parent

CONFIG_PATH = REPO_ROOT / "data/config/openclaw.json"
BROH_SOUL = REPO_ROOT / "data/workspace/broh/SOUL.md"
BROH_AGENTS = REPO_ROOT / "data/workspace/broh/AGENTS.md"

BROH_AGENT = {
    "id": "broh",
    "name": "broh",
    "description": "Compañero narrativo: perspectiva, continuidad y memoria personal no clínica",
    "workspace": "/home/node/.openclaw/workspace/broh",
    "agentDir": "/home/node/.openclaw/agents/broh/agent",
    "model": {
        "primary": "remote-lm/openclaw-remote",
        "fallbacks": ["remote-lm/openclaw-remote-coder"],
    },
    "identity": {
        "name": "Broh",
        "theme": "compañía, perspectiva y memoria narrativa",
        "emoji": "🤝",
    },
    "sandbox": {"mode": "off"},
    "tools": {
        "allow": ["read", "write", "exec", "message", "memory_search", "memory_get"],
        "exec": {
            "host": "gateway",
            "security": "full",
            "ask": "off",
            "strictInlineEval": True,
        },
    },
    "contextLimits": {
        "memoryGetMaxChars": 3500,
        "toolResultMaxChars": 4500,
        "postCompactionMaxChars": 2200,
    },
}


def backup(path: Path) -> None:
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_suffix(path.suffix + f".bak-broh-{stamp}"))


def patch_broh_agent(data: dict) -> None:
    agents = data.setdefault("agents", {}).setdefault("list", [])
    others = [agent for agent in agents if agent.get("id") != "broh"]
    existing = next((agent for agent in agents if agent.get("id") == "broh"), None)
    target = dict(BROH_AGENT)
    if existing:
        target.update({key: value for key, value in existing.items() if key not in target})
    data["agents"]["list"] = others + [target]

    active = (
        data.setdefault("plugins", {})
        .setdefault("entries", {})
        .setdefault("active-memory", {})
        .setdefault("config", {})
    )
    memory_agents = list(active.get("agents") or [])
    if "broh" not in memory_agents:
        memory_agents.append("broh")
    active["agents"] = memory_agents


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"ERROR: no existe {CONFIG_PATH}", file=sys.stderr)
        return 1
    backup(CONFIG_PATH)
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    patch_broh_agent(data)
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for path in (BROH_SOUL, BROH_AGENTS):
        if not path.exists():
            print(f"ERROR: no existe {path}", file=sys.stderr)
            return 1

    print(json.dumps({"ok": True, "agent": "broh", "config": str(CONFIG_PATH)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
