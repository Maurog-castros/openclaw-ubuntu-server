"""Delegación determinística agente care (/care)."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent
SCR = ROOT / "scripts"
RUN = SCR / "run-vida-py.sh"

sys.path.insert(0, str(SCR))
from openclaw_cli import openclaw_argv
from vida_common import is_leaked_tool_call, truncate_whatsapp
from vida_selfcare import handle as handle_selfcare

CARE_TOOL_LEAK_FALLBACK = (
    "Fede: perdón, me trabé un momento. Cuéntame en una frase qué necesitas y te respondo directo."
)

CARE_PREFIX = re.compile(r"^\s*/care\b\s*", re.I)
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
INBOUND_CANDIDATES = [
    ROOT / "data/config/media/inbound",
    Path("/home/node/.openclaw/media/inbound"),
    Path("/home/mauro/openclaw-mauro/data/config/media/inbound"),
]
DIARY_EXPLICIT_RE = re.compile(
    r"(?:"
    r"^\s*diario\b|"
    r"\banota(?:r|lo|la|me)?\s+en\s+(?:el\s+)?diario\b|"
    r"\ban[oó]talo\s+en\s+(?:el\s+)?diario\b|"
    r"\bguarda(?:r|lo|la|me)?\s+en\s+(?:el\s+)?diario\b|"
    r"\bagrega(?:r|lo|la|me)?(?:\s+esto)?\s+a\s+mi\s+diario\b|"
    r"\bagrega(?:r|lo|la|me)?(?:\s+esto)?\s+(?:al|a\s+el)\s+diario\b|"
    r"\bañade(?:r|lo|la|me)?(?:\s+esto)?\s+a\s+mi\s+diario\b|"
    r"\bañade(?:r|lo|la|me)?(?:\s+esto)?\s+(?:al|a\s+el)\s+diario\b"
    r")",
    re.I,
)


def strip_prefix(text: str) -> str:
    return CARE_PREFIX.sub("", text or "").strip()


def latest_inbound_image(max_age_sec: int = 3600) -> Path | None:
    now = time.time()
    best: Path | None = None
    for inbound in INBOUND_CANDIDATES:
        if not inbound.exists():
            continue
        for p in inbound.iterdir():
            if not p.is_file() or p.suffix.lower() not in IMAGE_EXT:
                continue
            if (now - p.stat().st_mtime) > max_age_sec:
                continue
            if best is None or p.stat().st_mtime > best.stat().st_mtime:
                best = p
    return best


def run_script(script: str, *args: str, timeout: int = 200) -> dict:
    cmd = [str(RUN), str(SCR / script), *args, "--json"]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout, check=False)
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "ok", "whatsapp_reply": proc.stdout.strip()}
    else:
        payload = {"status": "error", "whatsapp_reply": proc.stderr.strip() or "Error en script care."}
    if payload.get("whatsapp_reply"):
        payload["whatsapp_reply"] = truncate_whatsapp(str(payload["whatsapp_reply"]))
    return payload


def run_json(cmd: list[str], timeout: int = 240) -> tuple[int, dict[str, Any], str, str]:
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout, check=False)
    payload: dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"whatsapp_reply": proc.stdout.strip()}
    return proc.returncode, payload, proc.stdout, proc.stderr


def care_session_key() -> str:
    peer = os.environ.get("OPENCLAW_USER_PEER", "").strip()
    if peer:
        return f"agent:care:whatsapp:direct:{peer}"
    return "agent:care:whatsapp:direct"


def run_care_conversation(body: str, session_key: str | None = None) -> dict:
    """Conversación care breve, sin cortar orientación útil."""
    session_key = session_key or care_session_key()
    cmd = openclaw_argv(
        "agent",
        "--local",
        "--agent",
        "care",
        "--session-key",
        session_key,
        "--message",
        body,
        "--json",
    )
    code, payload, _, stderr = run_json(cmd, timeout=180)
    reply = ""
    for item in payload.get("payloads") or []:
        if isinstance(item, dict) and item.get("text"):
            reply = str(item["text"]).strip()
            break
    if not reply:
        reply = str(payload.get("whatsapp_reply") or "").strip()
    if code != 0 or not reply:
        return {
            "status": "error",
            "whatsapp_reply": truncate_whatsapp(
                "No pude responder ahora. ¿Puedes contarme un poco más en una frase?"
            ),
            "stderr": stderr[-400:],
        }
    if is_leaked_tool_call(reply):
        fallback = handle_selfcare(body)
        if fallback and fallback.get("status") != "skip":
            return fallback
        return {"status": "ok", "whatsapp_reply": truncate_whatsapp(CARE_TOOL_LEAK_FALLBACK)}
    return {"status": "ok", "whatsapp_reply": truncate_whatsapp(reply)}


def health_export_ack() -> dict:
    """Acuse cuando llega media que no es imagen (ej. export.zip de Apple Health).

    El pipeline real (repo sync-smartwatch-xiaomi, cron download-sync) lee el ZIP
    desde el cache de Telegram de Hermes y lo importa al contexto de care. Aquí solo
    confirmamos recepción para no enrutar el archivo a la ruta de foto de examen.
    """
    return {
        "status": "ok",
        "whatsapp_reply": truncate_whatsapp(
            "Recibí tu archivo. Si es el export de Apple Health (exportar.zip), lo importo "
            "automáticamente y reviso tus métricas; te aviso cuando esté listo. "
            "Si era una foto de examen u orden, reenvíala como imagen y dime «examen». "
            "¿Cómo te sientes hoy?"
        ),
    }


def should_process_exam_photo(text: str, has_media: bool, image_path: str | None) -> bool:
    if has_media or image_path:
        return True
    lower = strip_prefix(text).lower()
    return any(k in lower for k in ("examen", "laboratorio", "orden", "agenda", "cita", "calendario", "toma"))


def route(text: str, *, has_media: bool = False, image_path: str | None = None) -> dict:
    body = strip_prefix(text)
    lower = body.lower()

    if should_process_exam_photo(text, has_media, image_path):
        latest = latest_inbound_image() if has_media else None
        img = image_path or (str(latest) if latest else None)
        if img:
            return run_script("vida_exam_appointment.py", "--image", img, "--text", body or text)
        if has_media:
            # Media presente pero sin imagen reciente: no es foto de examen.
            # Caso típico: export de Apple Health (exportar.zip) por Telegram.
            return health_export_ack()

    if not body:
        return run_script("vida_checkin.py")

    if lower.startswith("perfil") or "perfílame" in lower or lower.startswith("profile"):
        ans = body.split(maxsplit=1)[1] if len(body.split()) > 1 else ""
        args = ["--answer", ans] if ans else []
        return run_script("vida_profile.py", *args)

    if DIARY_EXPLICIT_RE.search(body):
        entry = DIARY_EXPLICIT_RE.sub("", body, count=1).strip(" :：-")
        return run_script("vida_diary.py", "--text", entry or body)

    selfcare = handle_selfcare(body)
    if selfcare and selfcare.get("status") != "skip":
        return selfcare

    if any(k in lower for k in ("medic", "pastilla", "farmaco", "fármaco")):
        return run_script("vida_meds.py")
    if any(k in lower for k in ("despensa", "refriger", "comida", "cena", "almuerzo", "desayuno")):
        mode = "update" if any(k in lower for k in ("tengo", "agreg", "hay")) else "suggest"
        return run_script("vida_pantry.py", "--text", body, "--mode", mode)
    if any(k in lower for k in ("calendario", "citas", "agenda")) and not any(
        k in lower for k in ("examen", "laboratorio", "orden")
    ):
        return run_script("vida_calendar.py")
    if any(k in lower for k in ("doctor", "medico", "médico")):
        return run_script("vida_calendar.py")
    if re.search(r"\b(?:inspir|frase\s+del\s+d[ií]a)\b", lower):
        return run_script("vida_inspire.py")
    if any(k in lower for k in ("ejercicio", "gym", "caminar", "movimiento")):
        return {
            "status": "ok",
            "whatsapp_reply": truncate_whatsapp(
                "10-20 min bastan: caminata, estiramientos o subir escaleras. "
                "Empieza pequeño; consistencia > intensidad."
            ),
        }

    # Conversación emocional / motivación / charla — agente care, sin diario automático
    return run_care_conversation(body)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--has-media", action="store_true")
    ap.add_argument("--image", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    latest = latest_inbound_image() if args.has_media else None
    image_path = args.image or (str(latest) if latest else None)
    payload = route(args.text, has_media=args.has_media, image_path=image_path)
    payload["agent"] = "care"
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload.get("whatsapp_reply", ""))


if __name__ == "__main__":
    main()
