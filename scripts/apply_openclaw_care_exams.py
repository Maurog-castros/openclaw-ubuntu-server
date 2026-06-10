#!/usr/bin/env python3
"""Despliega hardening de fotos de exámenes + Google Calendar write para agente care."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/mauro/openclaw-mauro")
CONFIG = ROOT / "data/config/openclaw.json"
WS = ROOT / "data/workspace/care"
SCR = ROOT / "scripts"
HERE = Path(__file__).resolve().parent

CARE_EXAM_PROMPT_SNIPPET = (
    "Fotos de órdenes/exámenes médicos con /care: PASO 1 OBLIGATORIO "
    "run-vida-py.sh vida_delegate.py --text \"<msg>\" [--has-media] --json -> copia whatsapp_reply. "
    "El script lee la imagen (visión Iamiko), extrae fecha/hora/exámenes y CREA evento en Google Calendar. "
    "PROHIBIDO tool image en /care. PROHIBIDO inventar que guardaste sin ejecutar delegate."
)

SOUL_EXAM_SECTION = """
## Órdenes médicas y exámenes (FOTOS)

Si Mauro envía foto de orden de laboratorio/exámenes:
1. SIEMPRE: `vida_delegate.py --text "<msg>" [--has-media] --json`
2. El script OCR lee fecha/hora manuscrita y lista de exámenes.
3. Crea evento en Google Calendar con glosa/detalle de cada examen.
4. Copia `whatsapp_reply` literal. NUNCA digas "guardado" sin delegate ok.

Si falta fecha/hora en la foto, pide que reenvíe o escriba: `/care cita 10/06/26 07:20`.
Si calendario no autorizado: indicar `vida_calendar_oauth.py auth-url`.
""".strip()


def patch_finanzas_delegate() -> None:
    path = SCR / "finanzas_delegate.py"
    text = path.read_text(encoding="utf-8")
    old = """    if CARE_RE.search(raw_text):
        code, payload, _, _ = run_json(py_cmd("vida_delegate.py", "--text", raw_text), timeout=120)
        payload.setdefault("agent", "care")
        emit(payload, as_json=args.json, agent="care", skip_menu=True)
        return"""
    new = """    if CARE_RE.search(raw_text):
        care_cmd = py_cmd("vida_delegate.py", "--text", raw_text)
        image_path = args.image or (str(latest_inbound_image()) if args.has_media else None)
        if args.has_media:
            care_cmd.append("--has-media")
        if image_path:
            care_cmd.extend(["--image", image_path])
        code, payload, _, _ = run_json(care_cmd, timeout=240)
        payload.setdefault("agent", "care")
        emit(payload, as_json=args.json, agent="care", skip_menu=True)
        return"""
    if old not in text:
        raise SystemExit("finanzas_delegate.py: bloque /care no encontrado")
    path.write_text(text.replace(old, new), encoding="utf-8")


def patch_openclaw_json() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))

    for agent in cfg.get("agents", {}).get("list", []):
        if agent.get("id") != "care":
            continue
        model = agent.setdefault("model", {})
        fallbacks = model.setdefault("fallbacks", [])
        if "remote-lm/openclaw-remote-vision" not in fallbacks:
            fallbacks.insert(0, "remote-lm/openclaw-remote-vision")

    def patch_prompt(sp: str) -> str:
        sp = sp.replace("care_delegate.py", "vida_delegate.py")
        sp = re.sub(
            r"PASO 1 si /care:[^.]*\.json",
            'PASO 1 si /care: /home/node/openclaw-mauro/scripts/run-vida-py.sh /home/node/openclaw-mauro/scripts/vida_delegate.py --text "<msg>" [--has-media] --json',
            sp,
        )
        if "órdenes/exámenes médicos" not in sp:
            sp = sp.replace(
                "Prefijo /care = agente care diario personal",
                f"Prefijo /care = agente care diario personal. {CARE_EXAM_PROMPT_SNIPPET}",
                1,
            )
        return sp

    for ch_key in ("telegram", "whatsapp"):
        ch = cfg.get("channels", {}).get(ch_key, {})
        for peer_cfg in ch.get("direct", {}).values():
            if "systemPrompt" in peer_cfg:
                peer_cfg["systemPrompt"] = patch_prompt(peer_cfg["systemPrompt"])

    bak = CONFIG.with_suffix(f".json.bak-care-exams-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(CONFIG, bak)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_soul() -> None:
    soul = WS / "SOUL.md"
    text = soul.read_text(encoding="utf-8")
    text = text.replace("care_delegate.py", "vida_delegate.py")
    if "Órdenes médicas y exámenes" not in text:
        text = text.rstrip() + "\n\n" + SOUL_EXAM_SECTION + "\n"
    cal_section = "## Calendario\n\n`vida_calendar.py` para citas médicas próximas."
    cal_new = (
        "## Calendario\n\n"
        "`vida_calendar.py` lista citas próximas.\n"
        "Fotos de órdenes de exámenes → `vida_exam_appointment.py` (OCR + crea evento).\n"
        "OAuth escritura: `vida_calendar_oauth.py auth-url`."
    )
    text = text.replace(cal_section, cal_new)
    soul.write_text(text, encoding="utf-8")

    tools = WS / "TOOLS.md"
    ttext = tools.read_text(encoding="utf-8")
    extra = "vida_exam_appointment.py, vida_exam_vision.py, vida_calendar_create.py, vida_calendar_oauth.py"
    if "vida_exam_appointment.py" not in ttext:
        ttext = ttext.replace("vida_checkin.py", f"vida_checkin.py, {extra}")
        tools.write_text(ttext, encoding="utf-8")


def copy_scripts() -> None:
    names = [
        "vida_calendar_common.py",
        "vida_exam_vision.py",
        "vida_exam_appointment.py",
        "vida_calendar_create.py",
        "vida_calendar_oauth.py",
        "vida_calendar.py",
        "vida_delegate.py",
    ]
    for name in names:
        src = HERE / name
        dst = SCR / name
        if src.exists() and src.resolve() != dst.resolve():
            shutil.copy2(src, dst)


def main() -> None:
    copy_scripts()
    patch_finanzas_delegate()
    patch_openclaw_json()
    patch_soul()
    (WS / "data").mkdir(parents=True, exist_ok=True)
    print("care exams hardening OK")


if __name__ == "__main__":
    main()
