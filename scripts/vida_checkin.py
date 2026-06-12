"""Check-in diario: ánimo + recordatorios."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from vida_common import ROOT, care_data, load_json, now_local, reply, truncate_whatsapp

SCR = ROOT / "scripts"
RUN = SCR / "run-vida-py.sh"


def run_script(script: str, *extra: str) -> str:
    cmd = [str(RUN), str(SCR / script), *extra, "--json"]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, check=False)
    try:
        return json.loads(proc.stdout).get("whatsapp_reply", "")
    except json.JSONDecodeError:
        return proc.stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    profile = load_json(care_data() / "profile.json", {})
    day = now_local().strftime("%Y-%m-%d")

    name = profile.get("name") or os.environ.get("OPENCLAW_USER_NAME", "amigo")
    if args.text:
        body = truncate_whatsapp(
            f"Gracias por contarlo, {name}. ¿Qué crees que más te está pesando hoy?"
        )
    else:
        body = truncate_whatsapp(
            f"Hola {name}, ¿cómo amaneciste? Una palabra o una frase corta me basta."
        )

    out = reply(body)
    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
