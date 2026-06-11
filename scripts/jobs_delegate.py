#!/usr/bin/env python3
"""Delegate /jobs y /postula — buscar, postular, informar CSV."""

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

PY = str(ROOT / ".venv-finanzas/bin/python")
LINKEDIN_PY = str(ROOT / ".venv-linkedin-intel/bin/python")
if os.name == "nt":
    PY = sys.executable
    LINKEDIN_PY = sys.executable
elif not Path(PY).exists():
    PY = "python3"
if os.name != "nt" and not Path(LINKEDIN_PY).exists():
    LINKEDIN_PY = PY
SCR = str(ROOT / "scripts")

INDEX_RE = re.compile(r"\b(index(?:ar)?\s+cv|cv\s+index|actualizar\s+cv)\b", re.I)
SEARCH_RE = re.compile(r"\b(buscar\s+linkedin|linkedin\s+jobs|vacantes?\s+linkedin|refresh\s+jobs)\b", re.I)
MATCH_RE = re.compile(
    r"\b(vacantes?|match|oportunidades?\s+laboral|trabajos?\s+para\s+mi|"
    r"que\s+puedo\s+postular|buscar\s+empleo|ofertas?\s+devops)\b",
    re.I,
)
APPLY_RE = re.compile(r"\b(aplicar|postular|postula)\b", re.I)
REPORT_RE = re.compile(
    r"\b(mis\s+postulaciones|postulaciones?\s+realizadas|historial\s+postul|"
    r"reporte\s+postul|donde\s+postul|vacantes?\s+postuladas?)\b",
    re.I,
)
OPS_RE = re.compile(
    r"\b(career\s*ops|evaluar|evalua|analiza|analizar|pipeline|oferta|jd|job\s+description)\b",
    re.I,
)
JOBS_PREFIX_RE = re.compile(r"^\s*/(?:jobs|postula)\b", re.I)


def run_json(cmd: list[str], timeout: int = 600) -> tuple[int, dict[str, Any], str, str]:
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout, check=False)
    payload: dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"whatsapp_reply": proc.stdout.strip()}
    return proc.returncode, payload, proc.stdout, proc.stderr


def run_intel(message: str, session_key: str) -> tuple[int, str, str, str]:
    cmd = [
        "openclaw", "agent", "--local", "--agent", "jobs",
        "--session-key", session_key, "--message", message, "--json",
    ]
    code, payload, stdout, stderr = run_json(cmd, timeout=180)
    reply = ""
    for item in payload.get("payloads") or []:
        if isinstance(item, dict) and item.get("text"):
            reply = str(item["text"]).strip()
            break
    if not reply:
        reply = str(payload.get("whatsapp_reply") or "").strip()
    return code, reply, stdout, stderr


def main() -> None:
    parser = argparse.ArgumentParser(description="Delegate Jobs agent")
    parser.add_argument("--text", required=True)
    parser.add_argument("--session-key", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    message = JOBS_PREFIX_RE.sub("", args.text or "").strip()
    if not message:
        message = "buscar linkedin vacantes devops"

    if INDEX_RE.search(message):
        code, payload, _, stderr = run_json([PY, f"{SCR}/jobs_cv_index.py", "--json"])
        if code != 0 and not payload.get("whatsapp_reply"):
            payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Index CV fallo: {stderr[-400:]}"}
        payload.setdefault("agent", "jobs")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    if REPORT_RE.search(message):
        code, payload, _, _ = run_json([PY, f"{SCR}/jobs_report.py", "--json"])
        payload.setdefault("agent", "jobs")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    if OPS_RE.search(message) or re.search(r"https?://\S+", message) or len(message) > 160:
        code, payload, _, stderr = run_json([PY, f"{SCR}/jobs_ops.py", "--text", message, "--json"], timeout=240)
        if code != 0 and not payload.get("whatsapp_reply"):
            payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Career ops fallo: {stderr[-500:]}"}
        payload.setdefault("agent", "jobs")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    if APPLY_RE.search(message):
        code, payload, _, stderr = run_json(
            [PY, f"{SCR}/jobs_apply.py", "--text", message, "--json"],
            timeout=900,
        )
        if code != 0 and not payload.get("whatsapp_reply"):
            payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Postular fallo: {stderr[-500:]}"}
        payload.setdefault("agent", "jobs")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    if SEARCH_RE.search(message) or (MATCH_RE.search(message) and "linkedin" in message.lower()):
        code, payload, _, stderr = run_json(
            [LINKEDIN_PY, f"{SCR}/jobs_linkedin_search.py", "--json"],
            timeout=600,
        )
        if code != 0 and not payload.get("whatsapp_reply"):
            payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Busqueda LinkedIn fallo: {stderr[-500:]}"}
        payload.setdefault("agent", "jobs")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    if MATCH_RE.search(message):
        code, payload, _, stderr = run_json([PY, f"{SCR}/jobs_match.py", "--text", message, "--json"], timeout=180)
        if code != 0 and not payload.get("whatsapp_reply"):
            payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Match fallo: {stderr[-400:]}"}
        payload.setdefault("agent", "jobs")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    session_key = args.session_key or f"agent:jobs:whatsapp:{int(time.time())}"
    code, reply, _, stderr = run_intel(message, session_key)
    if code != 0 or not reply:
        code, reply, _, stderr = run_intel("Responde breve para WhatsApp: " + message, session_key + ":retry")

    if code != 0:
        result = {
            "status": "error",
            "agent": "jobs",
            "stderr": stderr[-1000:],
            "whatsapp_reply": "Jobs: usa /jobs buscar linkedin → /jobs postular 1 → /jobs mis postulaciones",
        }
    else:
        result = {"status": "ok", "agent": "jobs", "session_key": session_key, "whatsapp_reply": reply or "Sin respuesta."}
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["whatsapp_reply"])


if __name__ == "__main__":
    main()
