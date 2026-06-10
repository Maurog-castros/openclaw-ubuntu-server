"""Registro diario."""
from __future__ import annotations

import argparse
import json

from vida_common import DATA, now_local, reply


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    day = now_local().strftime("%Y-%m-%d")
    path = DATA / "diary" / f"{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = now_local().strftime("%H:%M")
    line = f"- [{stamp}] {args.text.strip()}\n"
    with path.open("a", encoding="utf-8") as f:
        if path.stat().st_size == 0:
            f.write(f"# Diario {day}\n\n")
        f.write(line)

    out = reply(f"Anotado en tu diario ({day}). 🌿")
    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
