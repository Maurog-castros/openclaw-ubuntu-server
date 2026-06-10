#!/usr/bin/env python3
"""E2E routing: prefijo /agent y mensajes naturales sin prefijo."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCR = Path(__file__).resolve().parent
ROOT = SCR.parent
if str(SCR) not in sys.path:
    sys.path.insert(0, str(SCR))

from openclaw_message_router import clear_sticky_agent, detect_agent, explicit_prefix, save_sticky_agent

RUN = SCR / "run-finanzas-py.sh"
DELEGATE = SCR / "channel_delegate.py"


@dataclass
class Case:
    text: str
    expect_agent: str
    expect_not_miss: bool = True
    has_media: bool = False
    note: str = ""


CASES = [
    # Fin — sin prefijo
    Case("dame el saldo", "fin"),
    Case("cuales son los ultimos movimientos bancarios", "fin"),
    Case("transferencias recientes", "fin"),
    Case("cuanto gaste este mes", "fin"),
    Case("ultimas boletas", "fin"),
    # Fin — con prefijo
    Case("/fin saldo", "fin"),
    Case("/finanzas ultimas boletas", "fin"),
    Case("/fin cuanto gaste en junio", "fin"),
    # Care
    Case("me siento mal", "care"),
    Case("como estoy hoy", "care"),
    Case("/care diario", "care"),
    Case("/care medicamentos", "care"),
    # Supp
    Case("escanear logs", "supp"),
    Case("estado del sistema", "supp"),
    Case("/supp fix", "supp"),
    Case("arregla el gateway", "supp"),
    # Intel
    Case("radar de tendencias", "intel"),
    Case("/intel daily", "intel"),
    Case("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "intel"),
    Case("resumir este video de youtube https://youtu.be/abc12345678", "intel"),
    # Jobs / postulaciones
    Case("vacantes devops para mi perfil", "jobs"),
    Case("/postula match", "jobs"),
    Case("/jobs indexar cv", "jobs"),
    # Content
    Case("de que trata el ultimo post", "content"),
    Case("/content https://instagram.com/p/ABC123/", "content"),
]


def run_delegate(text: str, *, has_media: bool = False) -> dict:
    cmd = [str(RUN), str(DELEGATE), "--text", text, "--json"]
    if has_media:
        cmd.append("--has-media")
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=180, check=False)
    raw = proc.stdout.strip() or proc.stderr.strip()
    if proc.returncode == 2:
        return {"status": "delegate_miss", "whatsapp_reply": ""}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "error", "whatsapp_reply": raw[:200]}


def run_sticky_tests() -> int:
    failed = 0
    print("=== Sticky thread ===")
    clear_sticky_agent()

    save_sticky_agent("care")
    got = detect_agent("dame el saldo")
    ok = got == "care"
    if not ok:
        failed += 1
    print(f"  [{'OK' if ok else 'FAIL'}] sticky care + «dame el saldo» -> {got} (want care)")

    got = detect_agent("/fin saldo")
    ok = got == "fin"
    if not ok:
        failed += 1
    print(f"  [{'OK' if ok else 'FAIL'}] switch /fin saldo -> {got} (want fin)")

    got = detect_agent("motivame un poco")
    ok = got == "fin"
    if not ok:
        failed += 1
    print(f"  [{'OK' if ok else 'FAIL'}] sticky fin + «motivame» -> {got} (want fin)")

    clear_sticky_agent()
    got = detect_agent("dame el saldo")
    ok = got == "fin"
    if not ok:
        failed += 1
    print(f"  [{'OK' if ok else 'FAIL'}] sin sticky + «dame el saldo» -> {got} (want fin)")

    return failed


def main() -> int:
    failed = 0
    print("=== Intent detection ===")
    for case in CASES:
        clear_sticky_agent()
        got = detect_agent(case.text, has_media=case.has_media)
        prefix = explicit_prefix(case.text)
        ok = got == case.expect_agent
        mark = "OK" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{mark}] {case.text!r} -> {got} (want {case.expect_agent}, prefix={prefix})")

    failed += run_sticky_tests()
    clear_sticky_agent()

    print("\n=== Delegate e2e (fin/care/supp, sin LLM pesado) ===")
    light_cases = [c for c in CASES if c.expect_agent in ("fin", "care", "supp")]
    for case in light_cases:
        clear_sticky_agent()
        payload = run_delegate(case.text, has_media=case.has_media)
        status = payload.get("status", "?")
        miss = status == "delegate_miss"
        ok = (not miss) if case.expect_not_miss else miss
        mark = "OK" if ok else "FAIL"
        if not ok:
            failed += 1
        preview = (payload.get("whatsapp_reply") or "")[:60].replace("\n", " ")
        print(f"  [{mark}] {case.text!r} status={status} preview={preview!r}")

    print(f"\n{'PASS' if failed == 0 else 'FAIL'}: {failed} fallos")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
