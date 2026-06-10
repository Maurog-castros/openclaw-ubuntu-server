"""Administra reglas del monitor Gmail."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES_FILE = ROOT / "data/gmail_watch_rules.json"


def load_rules(path: Path) -> Dict[str, Any]:
    if not path.exists():
        from gmail_watch_agent import DEFAULT_RULES

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULT_RULES, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def save_rules(path: Path, rules: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_category(rules: Dict[str, Any], category_id: str) -> Dict[str, Any]:
    for category in rules.get("categories", []):
        if category.get("id") == category_id or category.get("label") == category_id:
            return category
    category = {
        "id": category_id,
        "label": category_id,
        "priority": 70,
        "keywords": [],
        "senders": [],
    }
    rules.setdefault("categories", []).append(category)
    return category


def add_unique(items: list[str], value: str) -> bool:
    value = value.strip()
    if not value:
        return False
    lowered = {item.lower() for item in items}
    if value.lower() in lowered:
        return False
    items.append(value)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Reglas Gmail watch.")
    parser.add_argument("--rules", default=str(DEFAULT_RULES_FILE))
    sub = parser.add_subparsers(dest="cmd", required=True)

    add_sender = sub.add_parser("add-sender")
    add_sender.add_argument("--category", required=True)
    add_sender.add_argument("--sender", required=True)
    add_sender.add_argument("--label", default="")

    add_keyword = sub.add_parser("add-keyword")
    add_keyword.add_argument("--category", required=True)
    add_keyword.add_argument("--keyword", required=True)
    add_keyword.add_argument("--label", default="")

    sub.add_parser("list")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    path = Path(args.rules)
    rules = load_rules(path)
    changed = False
    if args.cmd == "add-sender":
        category = find_category(rules, args.category)
        if args.label:
            category["label"] = args.label
        changed = add_unique(category.setdefault("senders", []), args.sender)
    elif args.cmd == "add-keyword":
        category = find_category(rules, args.category)
        if args.label:
            category["label"] = args.label
        changed = add_unique(category.setdefault("keywords", []), args.keyword)

    if changed:
        save_rules(path, rules)

    result = {"status": "ok", "changed": changed, "rules": rules}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"changed={changed}")


if __name__ == "__main__":
    main()
