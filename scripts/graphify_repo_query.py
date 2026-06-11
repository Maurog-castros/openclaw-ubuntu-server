#!/usr/bin/env python3
"""Fast local lookup over graphify-out/query-index.json for /supp."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path("/home/mauro/Dev/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent

INDEX = ROOT / "graphify-out/query-index.json"
STOPWORDS = {
    "como",
    "donde",
    "para",
    "porque",
    "cual",
    "cuales",
    "esto",
    "esta",
    "este",
    "agent",
    "agente",
    "openclaw",
    "repo",
    "codigo",
    "archivo",
    "script",
    "flujo",
}


def terms(query: str) -> list[str]:
    raw = re.findall(r"[a-zA-Z0-9_./+-]{3,}", (query or "").lower())
    out = []
    for item in raw:
        if item in STOPWORDS:
            continue
        out.append(item.strip("./"))
    return list(dict.fromkeys(x for x in out if x))


def score_item(item: dict[str, Any], query_terms: list[str]) -> int:
    text = str(item.get("text") or "")
    source = str(item.get("source_file") or "").lower()
    score = 0
    for term in query_terms:
        if term in text:
            score += 4
        if term in str(item.get("label") or "").lower():
            score += 3
        if term in source:
            score += 5
    if source.startswith("scripts/"):
        score += 8
    if source.startswith("data/workspace/"):
        score += 6
    if source.startswith("data/config/extensions/"):
        score += 6
    if source.startswith("openclaw/"):
        score -= 4
    joined = " ".join(query_terms)
    if any(term in joined for term in ("whatsapp", "router", "route", "delegate")):
        if any(name in source for name in ("channel_delegate.py", "openclaw_message_router.py", "channel-delegate-hook")):
            score += 18
    if "jobs" in query_terms and any(name in source for name in ("jobs_delegate.py", "jobs_ops.py", "jobs_match.py")):
        score += 14
    if "care" in query_terms and any(name in source for name in ("vida_delegate.py", "vida_selfcare.py")):
        score += 14
    if "supp" in query_terms and "support_" in source:
        score += 14
    return score


def search(query: str, limit: int = 6) -> list[dict[str, Any]]:
    if not INDEX.exists():
        raise FileNotFoundError("No hay indice graphify. Ejecuta scripts/graphify_repo_refresh.sh")
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    query_terms = terms(query)
    if not query_terms:
        return []
    scored = []
    for item in data.get("items") or []:
        score = score_item(item, query_terms)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item | {"score": score} for score, item in scored[:limit]]


def format_reply(query: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Supp Graph: sin matches en índice. Prueba con nombre de script/agente más específico."
    lines = ["Supp Graph: contexto probable"]
    for row in rows:
        loc = row.get("source_location") or ""
        src = row.get("source_file") or "?"
        label = row.get("label") or "?"
        where = f"{src} {loc}".strip()
        lines.append(f"• {where}: {label[:70]}")
    return "\n".join(lines[:7])


def main() -> None:
    parser = argparse.ArgumentParser(description="Query compact graphify index")
    parser.add_argument("--text", required=True)
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        rows = search(args.text, limit=args.limit)
        payload = {
            "status": "ok",
            "agent": "supp",
            "matches": rows,
            "whatsapp_reply": format_reply(args.text, rows),
        }
    except Exception as exc:
        payload = {
            "status": "error",
            "agent": "supp",
            "whatsapp_reply": f"Supp Graph: {exc}",
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["whatsapp_reply"])


if __name__ == "__main__":
    main()
