"""Responde preguntas sobre el ultimo post IG analizado (sin historial de chat)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from content_instagram_analyze import build_whatsapp_reply, _caption_excerpt
from finanzas_common import resolve_data_path

DEFAULT_REF_DIR = "data/workspace/marketing/content/references/instagram"


def latest_analysis(refs_dir: Path) -> dict:
    files = sorted(
        refs_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in files:
        if path.name.endswith(".json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if data.get("url") or data.get("caption"):
                data["_meta_path"] = str(path)
                return data
    return {}


def build_followup_reply(data: dict) -> str:
    author = data.get("author") or "desconocido"
    url = data.get("url", "")
    caption = data.get("caption") or ""
    vision = data.get("vision_analysis") or {}

    lines = [f"El ultimo post que revisamos es de @{author}:", ""]

    if vision and not vision.get("error") and vision.get("tema"):
        lines.append(f"Tema: {vision['tema']}")
    elif vision.get("texto_visible"):
        lines.append(f"Tema: {vision['texto_visible']}")
    excerpt = _caption_excerpt(caption, 900)
    if excerpt:
        lines.append("")
        lines.append("De qué va:")
        lines.append(excerpt)
    if vision.get("estructura"):
        lines.append("")
        lines.append(f"Formato: {vision['estructura']}")

    lines.append("")
    lines.append(f"Link: {url}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ultimo analisis Instagram guardado.")
    parser.add_argument("--refs-dir", default=DEFAULT_REF_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    refs_dir = resolve_data_path(args.refs_dir)
    data = latest_analysis(refs_dir)
    if not data:
        payload = {
            "status": "not_found",
            "message": "No hay analisis IG guardado. Pega el link del post primero.",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["message"])
        sys.exit(1)

    payload = {
        "status": "ok",
        "shortcode": data.get("shortcode", ""),
        "url": data.get("url", ""),
        "author": data.get("author", ""),
        "whatsapp_reply": build_followup_reply(data),
        "full_reply": data.get("whatsapp_reply") or build_whatsapp_reply(data),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["whatsapp_reply"])


if __name__ == "__main__":
    main()
