"""Procesa la boleta mas reciente (WhatsApp/Telegram) y devuelve respuesta compacta."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import os

from finanzas_common import (
    DEFAULT_RECEIPTS_REGISTRY,
    DEFAULT_UNIFIED_CSV,
    DEFAULT_VISION_CSV,
    resolve_data_path,
)


def _inbound_dir() -> Path:
    override = os.environ.get("OPENCLAW_USER_INBOUND_DIR", "").strip()
    if override:
        return Path(override)
    return _REPO_ROOT / "data/config/media/inbound"


def format_whatsapp_reply(result: Dict[str, Any]) -> str:
    status = result.get("status")
    if status == "rejected":
        return result.get("message") or "Imagen no procesada como boleta."
    if status == "skipped":
        reason = result.get("reason") or "duplicada"
        parsed = result.get("parsed") or {}
        store = parsed.get("store") or (result.get("existing") or {}).get("store") or "comercio"
        return f"Boleta ya registrada ({reason}). Comercio previo: {store}."
    if status != "processed":
        return result.get("message") or result.get("summary") or json.dumps(result, ensure_ascii=False)

    lines = [
        "Boleta procesada:",
        f"Comercio: {result.get('store') or 'desconocido'}",
        f"Total: ${int(result.get('ticket_total') or 0):,}".replace(",", "."),
    ]
    validation = result.get("validation") or {}
    if not validation.get("ok"):
        issues = ", ".join(validation.get("issues") or [])
        lines.append(f"Advertencia OCR: {issues}")

    lines.append("Productos:")
    for idx, item in enumerate(result.get("items") or [], start=1):
        amount = int(item.get("amount") or 0)
        product = item.get("product") or "item"
        lines.append(f"{idx}. {product} — ${amount:,}".replace(",", "."))

    merge = result.get("merge")
    if isinstance(merge, dict) and merge.get("rows_written"):
        lines.append(f"Agregada al CSV unificado ({merge.get('rows_written')} lineas).")
    return "\n".join(lines)


def append_saldo_footer() -> str:
    script = _SCRIPTS_DIR / "finanzas_saldo.py"
    proc = subprocess.run(
        [sys.executable, str(script), "report", "--json"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(_REPO_ROOT),
    )
    if proc.returncode != 0:
        return ""
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return ""
    summary = payload.get("whatsapp_reply") or payload.get("summary") or ""
    if not summary:
        return ""
    return "\n\n---\n" + summary


def route_saldo_if_applicable(text: str, image: str | None) -> Dict[str, Any] | None:
    """Redirige capturas de saldo Santander que llegaron por error a receipt."""
    try:
        from finanzas_delegate import should_process_saldo

        if not should_process_saldo(text, bool(image), image):
            return None
    except ImportError:
        return None

    saldo_script = _SCRIPTS_DIR / "finanzas_saldo_whatsapp.py"
    cmd = [sys.executable, str(saldo_script), "--text", text or "", "--json"]
    if image:
        cmd.extend(["--image", image])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(_REPO_ROOT))
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR boleta inbound -> JSON + whatsapp_reply.")
    parser.add_argument("--text", default="", help="Caption/mensaje del usuario (para detectar saldo).")
    parser.add_argument("--image", help="Ruta explicita a imagen (opcional).")
    parser.add_argument(
        "--inbound-dir",
        default="",
        help="Carpeta media inbound (default: data/config/media/inbound).",
    )
    parser.add_argument(
        "--source",
        default="whatsapp_foto",
        choices=["telegram_foto", "whatsapp_foto", "openclaw_web", "manual"],
    )
    parser.add_argument("--merge", action="store_true", default=True)
    parser.add_argument("--no-merge", action="store_false", dest="merge")
    parser.add_argument("--reply-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    saldo_payload = route_saldo_if_applicable(args.text or "", args.image)
    if saldo_payload:
        reply = saldo_payload.get("whatsapp_reply") or saldo_payload.get("summary") or ""
        if args.reply_only:
            print(reply)
            return
        if args.json:
            print(json.dumps({**saldo_payload, "whatsapp_reply": reply}, ensure_ascii=False, indent=2))
        else:
            print(reply)
        return

    vision_script = _SCRIPTS_DIR / "receipt_vision_agent.py"
    cmd = [
        sys.executable,
        str(vision_script),
        "--source",
        args.source,
        "--merge" if args.merge else "",
        "--unified-output",
        str(resolve_data_path(DEFAULT_UNIFIED_CSV)),
        "--output",
        str(resolve_data_path(DEFAULT_VISION_CSV)),
        "--registry",
        str(resolve_data_path(DEFAULT_RECEIPTS_REGISTRY)),
        "--lider-input",
        str(_REPO_ROOT / "data/lider_receipts.csv"),
        "--transferencias-input",
        str(_REPO_ROOT / "data/transferencias.csv"),
        "--json",
    ]
    cmd = [part for part in cmd if part]
    if (args.text or "").strip():
        cmd.extend(["--user-caption", args.text.strip()])
    if args.image:
        cmd.extend(["--image", args.image])
    else:
        inbound = args.inbound_dir or str(_inbound_dir())
        cmd.extend(["--latest-inbound", "--inbound-dir", inbound])

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(_REPO_ROOT))
    raw = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode != 0:
        payload = {"status": "error", "message": raw[:800]}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else raw[:800])
        sys.exit(proc.returncode or 1)

    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"status": "error", "message": raw[:800]}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else raw[:800])
        sys.exit(1)

    reply = format_whatsapp_reply(result)
    payload = {**result, "whatsapp_reply": reply}
    if result.get("status") == "processed":
        footer = append_saldo_footer()
        if footer:
            reply = reply + footer
            payload["whatsapp_reply"] = reply
    if args.reply_only:
        print(reply)
        return
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(reply)


if __name__ == "__main__":
    main()
