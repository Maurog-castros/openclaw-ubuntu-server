#!/usr/bin/env python3
"""Routing de modelos OpenClaw: OpenRouter primario, iamiko con contexto >=64K.

Hermes (ia.iamiko.cl) rechaza modelos con ventana <64K. sync-openclaw-models.sh
antes reseteaba primary=openclaw-remote y contextWindow=32768 en todos los agentes.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO / "data/config/openclaw.json"
if not CONFIG_PATH.exists():
    CONFIG_PATH = Path("/home/mauro/openclaw-mauro/data/config/openclaw.json")

IAMIKO_CONTEXT = 131_072
OPENROUTER_CONTEXT = 200_000

TOOL_AGENTS = frozenset(
    {
        "main",
        "intel",
        "content",
        "sales",
        "pyme-chile",
        "hl-miko-web",
        "supp",
        "care",
        "jobs",
        "hlgo",
        "fin",
        "broh",
        "jenki",
    }
)

TOOL_PRIMARY = "remote-lm/openrouter-auto"
TOOL_FALLBACKS = [
    "remote-lm/openclaw-remote",
    "remote-lm/openclaw-remote-coder",
    "remote-lm/openclaw-remote-vision",
]

OPENROUTER_MODELS: list[dict[str, Any]] = [
    {
        "id": "openrouter-auto",
        "name": "OpenRouter auto (primario tool-calling)",
        "contextWindow": OPENROUTER_CONTEXT,
        "maxTokens": 8192,
    },
    {
        "id": "openrouter-gemini",
        "name": "OpenRouter Gemini 2.5 Flash",
        "contextWindow": 1_048_576,
        "maxTokens": 8192,
    },
    {
        "id": "openrouter-free",
        "name": "OpenRouter free tier",
        "contextWindow": OPENROUTER_CONTEXT,
        "maxTokens": 8192,
    },
    {
        "id": "openrouter-gemma",
        "name": "OpenRouter Gemma 4 31B free",
        "contextWindow": OPENROUTER_CONTEXT,
        "maxTokens": 8192,
    },
]

IAMIKO_CHAT_IDS = frozenset(
    {"openclaw-remote", "openclaw-remote-coder", "openclaw-remote-vision"}
)


def backup(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = path.with_suffix(path.suffix + f".bak-modelfix-{stamp}")
    shutil.copy2(path, dest)
    return dest


def model_entry(
    model_id: str,
    name: str,
    *,
    context_window: int,
    max_tokens: int = 8192,
    inputs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": model_id,
        "name": name,
        "reasoning": False,
        "input": inputs or ["text"],
        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        "contextWindow": context_window,
        "maxTokens": max_tokens,
    }


def tool_model_block() -> dict[str, Any]:
    return {"primary": TOOL_PRIMARY, "fallbacks": list(TOOL_FALLBACKS)}


def patch_models_catalog(data: dict[str, Any]) -> dict[str, int]:
    stats = {"iamiko_bumped": 0, "openrouter_added": 0}
    provider = data.setdefault("models", {}).setdefault("providers", {}).setdefault("remote-lm", {})
    models: list[dict[str, Any]] = list(provider.get("models") or [])
    by_id = {m.get("id"): m for m in models if m.get("id")}

    for model in models:
        mid = model.get("id")
        if mid in IAMIKO_CHAT_IDS and model.get("contextWindow", 0) < 64_000:
            model["contextWindow"] = IAMIKO_CONTEXT
            stats["iamiko_bumped"] += 1

    for spec in OPENROUTER_MODELS:
        mid = spec["id"]
        if mid in by_id:
            by_id[mid]["contextWindow"] = max(by_id[mid].get("contextWindow", 0), spec["contextWindow"])
            continue
        models.append(model_entry(mid, spec["name"], context_window=spec["contextWindow"]))
        stats["openrouter_added"] += 1

    provider["models"] = models
    return stats


def patch_agent_routing(data: dict[str, Any]) -> dict[str, int]:
    stats = {"defaults": 0, "agents": 0}
    agents = data.setdefault("agents", {})
    defaults = agents.setdefault("defaults", {})
    defaults["model"] = tool_model_block()
    stats["defaults"] = 1

    for agent in agents.get("list") or []:
        if not isinstance(agent, dict):
            continue
        aid = agent.get("id")
        if aid in TOOL_AGENTS:
            agent["model"] = tool_model_block()
            stats["agents"] += 1
    return stats


def apply_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "config": str(path),
        "backup": str(backup(path)),
        "models": patch_models_catalog(data),
        "routing": patch_agent_routing(data),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=CONFIG_PATH)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.config.exists():
        print(f"Config not found: {args.config}", file=sys.stderr)
        return 1

    data = json.loads(args.config.read_text(encoding="utf-8"))
    model_stats = patch_models_catalog(data)
    route_stats = patch_agent_routing(data)
    report = {
        "config": str(args.config),
        "models": model_stats,
        "routing": route_stats,
        "primary": TOOL_PRIMARY,
    }

    if args.dry_run:
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    report["backup"] = str(backup(args.config))
    args.config.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Applied model routing -> {args.config}")
        print(f"Backup: {report['backup']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
