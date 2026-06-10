#!/usr/bin/env python3
"""Configura agente content + delegacion WhatsApp desde finanzas."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path("/home/mauro/openclaw-mauro")
CONFIG_PATH = REPO_ROOT / "data/config/openclaw.json"
CONTENT_SOUL_PATH = REPO_ROOT / "data/workspace/marketing/content/SOUL.md"
FINANZAS_SOUL_PATH = REPO_ROOT / "data/workspace/marketing/finanzas/SOUL.md"
CONTENT_APPEND = REPO_ROOT / "config/marketing/content-SOUL-whatsapp.md"
FINANZAS_APPEND = REPO_ROOT / "config/marketing/finanzas-SOUL-content-delegate.md"
INSTAGRAM_DRAFTS = REPO_ROOT / "data/workspace/marketing/content/drafts/instagram"

CONTENT_AGENT_PATCH = {
    "description": "Contenido y redes: borradores con Intel, aprobacion antes de publicar",
    "tools": {
        "allow": [
            "read",
            "write",
            "edit",
            "exec",
            "message",
            "image",
            "web_search",
            "memory_search",
            "memory_get",
        ],
        "exec": {
            "host": "gateway",
            "ask": "on-miss",
            "strictInlineEval": True,
            "commandHighlighting": True,
        },
    },
}

CHANNEL_CONTENT_HINT = (
    "WhatsApp: link Instagram -> ejecutar content_instagram_whatsapp.py --text \"<msg>\" --json. "
    "Prefijo /content = Drift. /fin = finanzas. Drift NUNCA diga que no puede abrir Instagram."
)


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = path.with_suffix(path.suffix + f".bak-content-{stamp}")
    shutil.copy2(path, dest)
    return dest


def upsert_marker_section(target: Path, source: Path, marker: str) -> bool:
    if not source.exists():
        return False
    block = source.read_text(encoding="utf-8").strip() + "\n"
    current = target.read_text(encoding="utf-8") if target.exists() else ""
    if marker in current:
        before, _, after = current.partition(marker)
        tail_idx = after.find("\n<!--")
        tail = after[tail_idx + 1 :] if tail_idx >= 0 else ""
        new_text = before.rstrip() + "\n\n" + block + (("\n" + tail.lstrip()) if tail else "")
    else:
        new_text = (current.rstrip() + "\n\n" + block) if current.strip() else block
    if new_text == current:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_text, encoding="utf-8")
    return True


def patch_content_agent(data: dict) -> bool:
    changed = False
    for agent in data.get("agents", {}).get("list", []):
        if agent.get("id") != "content":
            continue
        for key, value in CONTENT_AGENT_PATCH.items():
            if agent.get(key) != value:
                agent[key] = value
                changed = True
        tools = agent.setdefault("tools", {})
        allow = tools.setdefault("allow", [])
        for tool in CONTENT_AGENT_PATCH["tools"]["allow"]:
            if tool not in allow:
                allow.append(tool)
                changed = True
        exec_cfg = tools.setdefault("exec", {})
        for k, v in CONTENT_AGENT_PATCH["tools"]["exec"].items():
            if exec_cfg.get(k) != v:
                exec_cfg[k] = v
                changed = True
        return changed
    return changed


def patch_whatsapp_hint(data: dict) -> bool:
    whatsapp = data.get("channels", {}).get("whatsapp", {})
    direct = whatsapp.get("direct", {})
    wildcard = direct.get("*", {})
    current = wildcard.get("systemPrompt", "")
    if CHANNEL_CONTENT_HINT in current:
        return False
    hint = f"{CHANNEL_CONTENT_HINT}\n\n{current}".strip() if current else CHANNEL_CONTENT_HINT
    wildcard["systemPrompt"] = hint
    direct["*"] = wildcard
    whatsapp["direct"] = direct
    data.setdefault("channels", {})["whatsapp"] = whatsapp
    return True


def main() -> None:
    if not CONFIG_PATH.exists():
        raise SystemExit(f"No existe {CONFIG_PATH}")

    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    backup(CONFIG_PATH)

    changes = {
        "content_soul": upsert_marker_section(CONTENT_SOUL_PATH, CONTENT_APPEND, "<!-- WHATSAPP_WORKFLOW -->"),
        "finanzas_delegate": upsert_marker_section(FINANZAS_SOUL_PATH, FINANZAS_APPEND, "<!-- CONTENT_DELEGATE -->"),
        "content_agent": patch_content_agent(data),
        "whatsapp_hint": patch_whatsapp_hint(data),
    }

    INSTAGRAM_DRAFTS.mkdir(parents=True, exist_ok=True)

    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "changes": changes,
                "instagram_drafts": str(INSTAGRAM_DRAFTS),
                "restart_hint": "cd openclaw && docker compose -f docker-compose.yml -f docker-compose.finanzas-mounts.yml up -d openclaw-gateway",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
