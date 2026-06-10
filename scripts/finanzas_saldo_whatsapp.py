"""Saldo Santander desde mensaje WhatsApp (texto o screenshot)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_saldo import parse_balance_text, wants_set_actual

SALDO_REPORT_RE = re.compile(
    r"(?:saldo|cuenta|santander|disponible|tengo|real|app|screenshot|captura)",
    re.I,
)


def infer_mode(text: str, *, has_image: bool) -> str:
    if parse_balance_text(text or ""):
        return "set-actual"
    if has_image:
        return "set-actual-image"
    if SALDO_REPORT_RE.search(text or ""):
        return "report"
    return "report"


def run_saldo_cmd(extra_args: list[str]) -> Dict[str, Any]:
    script = _SCRIPTS_DIR / "finanzas_saldo.py"
    cmd = [sys.executable, str(script), *extra_args, "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(_REPO_ROOT))
    raw = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode != 0:
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"status": "error", "message": raw[:800]}
    return json.loads(proc.stdout)


def run_balance_ocr(image_path: Path) -> Dict[str, Any]:
    script = _SCRIPTS_DIR / "finanzas_saldo_screenshot.py"
    if not script.exists():
        return {}
    proc = subprocess.run(
        [sys.executable, str(script), "--image", str(image_path), "--json"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(_REPO_ROOT),
    )
    if proc.returncode != 0:
        return {}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}
    if payload.get("status") != "ok":
        return {}
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Saldo Santander — wrapper WhatsApp.")
    parser.add_argument("--text", default="", help="Mensaje del usuario.")
    parser.add_argument("--amount", type=int, default=0, help="Monto CLP entero (sin $ ni puntos).")
    parser.add_argument("--image", help="Screenshot app Santander (opcional).")
    parser.add_argument("--reply-only", action="store_true")
    parser.add_argument("--report-only", action="store_true", help="Solo consulta; nunca set-actual.")
    parser.add_argument("--short", action="store_true", help="Respuesta corta (menu Ver saldo).")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    text = args.text or ""
    has_image = bool(args.image)
    explicit_amount = int(args.amount) if args.amount and args.amount > 0 else None
    text_amount = explicit_amount or (
        parse_balance_text(text) if wants_set_actual(text, has_image=has_image, explicit_amount=bool(explicit_amount)) else None
    )
    if args.report_only:
        mode = "report"
    elif text_amount and wants_set_actual(text, has_image=has_image, explicit_amount=bool(explicit_amount)):
        mode = "set-actual"
    else:
        mode = infer_mode(text, has_image=has_image)

    if mode == "set-actual-image" and args.image and not explicit_amount and not parse_balance_text(text):
        ocr = run_balance_ocr(Path(args.image))
        amount = text_amount or int(ocr.get("balance_clp") or 0) or None
        if amount is None:
            result = {
                "status": "error",
                "message": "No pude leer el saldo del screenshot. Dime el monto en texto.",
            }
        else:
            source = "user_manual" if text_amount else "user_screenshot"
            cmd = ["set-actual", "--amount", str(amount), "--source", source]
            as_of = (ocr.get("as_of_date") or "").strip()[:10]
            if as_of and not text_amount:
                cmd.extend(["--as-of-date", as_of])
            result = run_saldo_cmd(cmd)
    elif mode == "set-actual" or text_amount:
        if text_amount:
            result = run_saldo_cmd(
                ["set-actual", "--amount", str(text_amount), "--source", "user_manual"]
            )
        else:
            result = run_saldo_cmd(["set-actual", "--text", text, "--source", "user_manual"])
    else:
        cmd = ["report"]
        if text:
            cmd.extend(["--text", text])
        if args.short:
            cmd.append("--short")
        result = run_saldo_cmd(cmd)

    reply = result.get("whatsapp_reply") or result.get("summary") or result.get("message") or ""
    if args.reply_only:
        print(reply)
        return
    if args.json:
        payload = {**result, "whatsapp_reply": reply}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(reply)


if __name__ == "__main__":
    main()
