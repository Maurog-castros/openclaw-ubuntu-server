#!/usr/bin/env python3
"""Build a compact query index from graphify-out/graph.json."""

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

GRAPH = ROOT / "graphify-out/graph.json"
INDEX = ROOT / "graphify-out/query-index.json"
SOURCE_PREFIXES = (
    "scripts/",
    "data/workspace/",
    "data/config/extensions/",
    "config/",
    "docs/",
    "openclaw/",
    "README",
    "AGENTS",
)


def useful_node(node: dict[str, Any]) -> bool:
    source = str(node.get("source_file") or "")
    if not source:
        return False
    if source.startswith("graphify-out/"):
        return False
    return source.startswith(SOURCE_PREFIXES)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def build_index(limit: int = 250_000) -> dict[str, Any]:
    if not GRAPH.exists():
        raise FileNotFoundError(f"No existe {GRAPH}")
    data = json.loads(GRAPH.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = []
    for node in data.get("nodes") or []:
        if not isinstance(node, dict) or not useful_node(node):
            continue
        label = normalize_text(str(node.get("label") or node.get("id") or ""))
        source = normalize_text(str(node.get("source_file") or ""))
        location = normalize_text(str(node.get("source_location") or ""))
        if not label or not source:
            continue
        items.append(
            {
                "id": node.get("id"),
                "label": label[:180],
                "source_file": source,
                "source_location": location,
                "file_type": node.get("file_type") or "",
                "community": node.get("community"),
                "text": f"{label} {source} {location}".lower()[:500],
            }
        )
        if len(items) >= limit:
            break
    return {
        "built_from": str(GRAPH.relative_to(ROOT)),
        "built_at_commit": data.get("built_at_commit", ""),
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create compact graphify query index")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    index = build_index()
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out = {"status": "ok", "index": str(INDEX), "items": len(index["items"])}
    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out)


if __name__ == "__main__":
    main()
