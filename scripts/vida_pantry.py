"""Despensa/refrigerado y sugerencias de comida."""
from __future__ import annotations

import argparse
import json
import re

from vida_common import care_data, load_json, now_local, reply, save_json

MEAL_IDEAS = [
    ("huevos", "huevos", "revuelto con queso"),
    ("arroz", "arroz", "arroz con huevo frito"),
    ("fideos", "fideos", "fideos con mantequilla y queso"),
    ("atun", "atún", "atún con arroz y tomate"),
    ("tomates", "tomate", "ensalada simple con tomate y aceite"),
    ("queso", "queso", "tostadas con queso"),
    ("leche", "leche", "avena/cereal con leche si tienes"),
]


def update_pantry(text: str, pantry: dict) -> None:
    lower = text.lower()
    if "despensa" in lower or "tengo" in lower:
        parts = re.split(r"[,;\n]", text)
        for p in parts:
            p = p.strip().lower()
            if len(p) < 3:
                continue
            if any(x in p for x in ("despensa", "refriger", "tengo", "agreg")):
                continue
            target = pantry["refrigerado"] if "refri" in lower else pantry["despensa"]
            if p not in target:
                target.append(p)
    pantry["updated_at"] = now_local().isoformat()


def suggest(pantry: dict) -> str:
    all_items = [x.lower() for x in (pantry.get("despensa") or []) + (pantry.get("refrigerado") or [])]
    ideas = []
    for key, need, dish in MEAL_IDEAS:
        if any(key in item for item in all_items):
            ideas.append(f"• {dish}")
    if not ideas:
        return "Con lo que tienes, algo simple: huevos, arroz o fideos con lo que sobre."
    return "\n".join(ideas[:4])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="")
    ap.add_argument("--mode", choices=["update", "suggest"], default="suggest")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    pantry = load_json(care_data() / "pantry.json", {"despensa": [], "refrigerado": []})
    if args.mode == "update" or args.text:
        update_pantry(args.text, pantry)
        save_json(care_data() / "pantry.json", pantry)

    ideas = suggest(pantry)
    desp = ", ".join(pantry.get("despensa") or []) or "(vacía)"
    refr = ", ".join(pantry.get("refrigerado") or []) or "(vacío)"
    out = reply(f"*Despensa:* {desp}\n*Refrigerado:* {refr}\n\n*Ideas con lo que hay:*\n{ideas}")
    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
