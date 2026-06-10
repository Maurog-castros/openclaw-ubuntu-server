"""Un solo comando para WhatsApp: extrae URL Instagram del mensaje y analiza."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

INSTAGRAM_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|reels)/[A-Za-z0-9_-]+/?",
    re.I,
)

FOLLOWUP_RE = re.compile(
    r"(?:"
    r"ultim[oa]\s+post|ese\s+post|el\s+que\s+revisamos|"
    r"de\s+qu[eé]\s+trata|qu[eé]\s+dice|qu[eé]\s+dec[ií]a|"
    r"resumen\s+del\s+post|sobre\s+ese\s+post"
    r")",
    re.I,
)

INTEL_LINKEDIN_RE = re.compile(
    r"(?:"
    r"agente\s+intel|intel\s+linkedin|linkedin\s+intel|"
    r"contenido\s+(?:del\s+)?intel|intel\s+dejó|intel\s+dejo|"
    r"tendencias\s+linkedin|senales\s+linkedin|señales\s+linkedin|"
    r"borrador\s+linkedin|linkedin\s+tendencias|"
    r"que\s+dejo\s+intel|qu[eé]\s+dejo\s+intel"
    r")",
    re.I,
)


def is_followup_question(text: str) -> bool:
    return bool(FOLLOWUP_RE.search(text or ""))


def extract_url(text: str) -> str:
    match = INSTAGRAM_URL_RE.search(text or "")
    if not match:
        return ""
    return match.group(0).split("?")[0].rstrip("/") + "/"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analiza post Instagram desde texto WhatsApp (extrae URL)."
    )
    parser.add_argument("--text", required=True, help="Mensaje completo del usuario.")
    parser.add_argument("--vision-model", default="openclaw-remote-vision")
    parser.add_argument("--no-vision", action="store_true", help="Omitir analisis visual (mas rapido).")
    parser.add_argument(
        "--reply-only",
        action="store_true",
        help="Solo imprime whatsapp_reply (para pegar en WhatsApp).",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    url = extract_url(args.text)
    if not url and INTEL_LINKEDIN_RE.search(args.text):
        linkedin_script = _SCRIPTS_DIR / "linkedin_intel_format.py"
        proc = subprocess.run(
            [sys.executable, str(linkedin_script), "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "error").strip()[:500]
            payload = {"status": "error", "message": err}
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else err)
            sys.exit(proc.returncode or 1)
        payload = json.loads(proc.stdout)
        if args.reply_only:
            print(payload.get("whatsapp_reply", ""))
            return
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload.get("whatsapp_reply", ""))
        return

    if not url:
        if is_followup_question(args.text):
            last_script = _SCRIPTS_DIR / "content_instagram_last.py"
            proc = subprocess.run(
                [sys.executable, str(last_script), "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "error").strip()[:500]
                payload = {"status": "error", "message": err}
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else err)
                sys.exit(proc.returncode or 1)
            payload = json.loads(proc.stdout)
            if args.reply_only:
                print(payload.get("whatsapp_reply", ""))
                return
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(payload.get("whatsapp_reply", ""))
            return

        payload = {
            "status": "no_url",
            "message": "No encontré URL de Instagram (instagram.com/p/... o /reel/...).",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["message"])
        sys.exit(1)

    analyze_script = _SCRIPTS_DIR / "content_instagram_analyze.py"
    cmd = [
        sys.executable,
        str(analyze_script),
        "--url",
        url,
        "--vision-model",
        args.vision_model,
    ]
    if args.no_vision:
        cmd.append("--no-vision")
    cmd.append("--json")

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "error").strip()[:500]
        payload = {"status": "error", "url": url, "message": err}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else err)
        sys.exit(proc.returncode or 1)

    payload = json.loads(proc.stdout)
    if args.reply_only:
        print(payload.get("whatsapp_reply", payload.get("summary", "")))
        return
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload.get("whatsapp_reply", payload.get("summary", proc.stdout)))


if __name__ == "__main__":
    main()
