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

from jobs_profile import get_profile, list_profiles, parse_profile_from_text
from openclaw_cli import openclaw_argv

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
RECOMMENDED_RE = re.compile(r"\b(recommended|recomendad[oa]s?|jymbii|jobs\s+home)\b", re.I)
CHILETRABAJOS_RE = re.compile(r"\b(chiletrabajos|chile\s*trabajos)\b", re.I)
CHILETRABAJOS_LOGIN_RE = re.compile(r"\b(chiletrabajos\s+login|login\s+chiletrabajos)\b", re.I)
LABORUM_RE = re.compile(r"\b(laborum|sync\s+experiencia|experiencia\s+portal|curriculum\s+laborum)\b", re.I)
LABORUM_LOGIN_RE = re.compile(r"\b(laborum\s+login|login\s+laborum)\b", re.I)
PORTAL_PY = str(ROOT / ".venv-jobs-portals/bin/python")
if not Path(PORTAL_PY).exists():
    PORTAL_PY = PY
DECISION_RE = re.compile(r"\b(aprobar|approve|descartar|discard|estado|status)\b", re.I)
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
ON_DEMAND_REPORT_RE = re.compile(
    r"\b((reporte|informe)\s+(ahora|manual|on\s*demand|de\s+vacantes)|"
    r"(buscar|actualizar)\s+(vacantes?\s+)?ahora)\b",
    re.I,
)
OPS_RE = re.compile(
    r"\b(career\s*ops|evaluar|evalua|analiza|analizar|pipeline|oferta|jd|job\s+description)\b",
    re.I,
)
JOBS_PREFIX_RE = re.compile(r"^\s*/(?:jobs|postula)\b", re.I)
PROFILES_RE = re.compile(r"\b(perfiles\s+jobs|listar\s+perfiles|jobs\s+perfiles)\b", re.I)


def run_json(
    cmd: list[str],
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any], str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        env=env,
    )
    payload: dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"whatsapp_reply": proc.stdout.strip()}
    return proc.returncode, payload, proc.stdout, proc.stderr


def laborum_browser_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":11.0")
    env.setdefault("XAUTHORITY", "/home/mauro/.Xauthority")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/1000/bus")
    return env


def run_intel(message: str, session_key: str) -> tuple[int, str, str, str]:
    cmd = openclaw_argv(
        "agent", "--local", "--agent", "jobs",
        "--session-key", session_key, "--message", message, "--json",
    )
    code, payload, stdout, stderr = run_json(cmd, timeout=180)
    reply = ""
    for item in payload.get("payloads") or []:
        if isinstance(item, dict) and item.get("text"):
            reply = str(item["text"]).strip()
            break
    if not reply:
        reply = str(payload.get("whatsapp_reply") or "").strip()
    return code, reply, stdout, stderr


def jobs_env(profile_id: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if profile_id:
        env.update(get_profile(profile_id).env())
    return env


def run_recommended_on_demand(env: dict[str, str]) -> dict[str, Any]:
    source_warnings: list[str] = []
    code, payload, _, stderr = run_json(
        [LINKEDIN_PY, f"{SCR}/jobs_linkedin_recommended.py", "--json"],
        timeout=600,
        env=env,
    )
    if code != 0:
        return {
            "status": "error",
            "agent": "jobs",
            "whatsapp_reply": payload.get("whatsapp_reply")
            or f"Búsqueda manual LinkedIn falló: {stderr[-400:]}",
        }

    code, payload, _, _ = run_json(
        [LINKEDIN_PY, f"{SCR}/jobs_chiletrabajos_scrape.py", "--json"],
        timeout=300,
        env=env,
    )
    if code != 0:
        code, payload, _, stderr = run_json(
            [LINKEDIN_PY, f"{SCR}/jobs_chiletrabajos_scrape.py", "--no-session", "--json"],
            timeout=300,
            env=env,
        )
        if code != 0:
            source_warnings.append(payload.get("whatsapp_reply") or stderr[-300:])

    code, pipeline, _, stderr = run_json(
        [LINKEDIN_PY, f"{SCR}/jobs_recommended_pipeline.py", "--json"],
        timeout=900,
        env=env,
    )
    if code != 0:
        return {
            "status": "error",
            "agent": "jobs",
            "whatsapp_reply": pipeline.get("whatsapp_reply")
            or f"Análisis manual falló: {stderr[-400:]}",
        }

    code, digest, _, stderr = run_json(
        [PY, f"{SCR}/jobs_recommended_digest.py", "--json"],
        timeout=60,
        env=env,
    )
    if code != 0:
        return {
            "status": "error",
            "agent": "jobs",
            "whatsapp_reply": digest.get("whatsapp_reply")
            or f"Reporte manual falló: {stderr[-400:]}",
        }
    digest.update(
        {
            "status": "partial" if source_warnings else "ok",
            "agent": "jobs",
            "on_demand": True,
            "pipeline": {
                "processed": pipeline.get("processed", 0),
                "closed_excluded": len(pipeline.get("closed_excluded") or []),
                "errors": len(pipeline.get("errors") or []),
            },
            "source_warnings": source_warnings,
        }
    )
    if source_warnings:
        digest["whatsapp_reply"] += "\n\nAviso: ChileTrabajos no respondió; reporte basado en fuentes disponibles."
    return digest


def start_recommended_on_demand(env: dict[str, str]) -> dict[str, Any]:
    log_dir = ROOT / "runtime/logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "jobs-recommended-on-demand.log"
    with log_file.open("a", encoding="utf-8") as handle:
        proc = subprocess.Popen(
            [LINKEDIN_PY, f"{SCR}/jobs_recommended_on_demand.py"],
            cwd=str(ROOT),
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return {
        "status": "ok",
        "agent": "jobs",
        "on_demand": True,
        "pid": proc.pid,
        "whatsapp_reply": (
            "Búsqueda iniciada. Enviaré avance cada 5 segundos y el reporte final "
            "cuando termine."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Delegate Jobs agent")
    parser.add_argument("--text", required=True)
    parser.add_argument("--session-key", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    message = JOBS_PREFIX_RE.sub("", args.text or "").strip()
    message, profile_id = parse_profile_from_text(message)
    env = jobs_env(profile_id)

    if PROFILES_RE.search(message):
        payload = {
            "status": "ok",
            "agent": "jobs",
            "profiles": [
                {"id": p.profile_id, "label": p.label, "workspace": str(p.workspace)}
                for p in list_profiles()
            ],
            "whatsapp_reply": "Perfiles Jobs:\n" + "\n".join(
                f"@{p.profile_id} — {p.label}" for p in list_profiles()
            ) + "\n\nUsa: /jobs @perfil buscar linkedin",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["whatsapp_reply"])
        return

    if not message:
        message = "buscar linkedin vacantes devops"

    if INDEX_RE.search(message):
        code, payload, _, stderr = run_json([PY, f"{SCR}/jobs_cv_index.py", "--json"], env=env)
        if code != 0 and not payload.get("whatsapp_reply"):
            payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Index CV fallo: {stderr[-400:]}"}
        payload.setdefault("agent", "jobs")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    if ON_DEMAND_REPORT_RE.search(message):
        payload = start_recommended_on_demand(env)
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    if REPORT_RE.search(message):
        code, payload, _, _ = run_json([PY, f"{SCR}/jobs_report.py", "--json"], env=env)
        payload.setdefault("agent", "jobs")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    decision = DECISION_RE.search(message)
    if decision:
        action_map = {"approve": "aprobar", "discard": "descartar", "status": "estado"}
        action = action_map.get(decision.group(1).lower(), decision.group(1).lower())
        job_match = re.search(r"\b\d{8,12}\b", message)
        cmd = [PY, f"{SCR}/jobs_approval.py", action]
        if job_match:
            cmd.append(job_match.group(0))
        cmd.append("--json")
        _, payload, _, stderr = run_json(cmd, timeout=60, env=env)
        if not payload.get("whatsapp_reply"):
            payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Decision Jobs fallo: {stderr[-400:]}"}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    if LABORUM_LOGIN_RE.search(message):
        payload = {
            "status": "ok",
            "agent": "jobs",
            "whatsapp_reply": (
                "Laborum login manual: DISPLAY=:11.0 "
                ".venv-jobs-portals/bin/python scripts/jobs_laborum_login.py login --headed"
            ),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["whatsapp_reply"])
        return

    if LABORUM_RE.search(message):
        apply_changes = bool(re.search(r"\b(aplicar|actualizar|sincronizar|confirmar)\b", message, re.I))
        cmd = [PORTAL_PY, f"{SCR}/jobs_laborum_sync.py", "--json"]
        if apply_changes:
            cmd.extend(["--apply", "--confirm", "UPDATE-LABORUM"])
        lab_env = laborum_browser_env()
        lab_env.update(env)
        _, payload, _, stderr = run_json(
            cmd,
            timeout=900,
            env=lab_env,
        )
        if not payload.get("whatsapp_reply"):
            payload = {
                "status": "error",
                "agent": "jobs",
                "whatsapp_reply": f"Laborum fallo: {stderr[-500:]}",
            }
        payload.setdefault("agent", "jobs")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["whatsapp_reply"])
        return

    if OPS_RE.search(message) or re.search(r"https?://\S+", message) or len(message) > 160:
        code, payload, _, stderr = run_json([PY, f"{SCR}/jobs_ops.py", "--text", message, "--json"], timeout=240, env=env)
        if code != 0 and not payload.get("whatsapp_reply"):
            payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Career ops fallo: {stderr[-500:]}"}
        payload.setdefault("agent", "jobs")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    if APPLY_RE.search(message):
        code, payload, _, stderr = run_json(
            [PY, f"{SCR}/jobs_apply.py", "--text", message, "--json"],
            timeout=900,
            env=env,
        )
        if code != 0 and not payload.get("whatsapp_reply"):
            payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Postular fallo: {stderr[-500:]}"}
        payload.setdefault("agent", "jobs")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    if CHILETRABAJOS_LOGIN_RE.search(message):
        proc = subprocess.run(
            [LINKEDIN_PY, f"{SCR}/jobs_chiletrabajos_login.py", "auto"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
            env=env,
        )
        reply = (proc.stdout or proc.stderr).strip() or "ChileTrabajos: sesion guardada."
        payload = {"status": "ok" if proc.returncode == 0 else "error", "agent": "jobs", "whatsapp_reply": reply[-900:]}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    if CHILETRABAJOS_RE.search(message):
        code, payload, _, stderr = run_json([LINKEDIN_PY, f"{SCR}/jobs_chiletrabajos_scrape.py", "--json"], timeout=300, env=env)
        if code != 0 and not payload.get("whatsapp_reply"):
            payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"ChileTrabajos fallo: {stderr[-500:]}"}
        payload.setdefault("agent", "jobs")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    if RECOMMENDED_RE.search(message) or SEARCH_RE.search(message) or (MATCH_RE.search(message) and "linkedin" in message.lower()):
        script = "jobs_linkedin_recommended.py" if RECOMMENDED_RE.search(message) else "jobs_linkedin_search.py"
        code, payload, _, stderr = run_json(
            [LINKEDIN_PY, f"{SCR}/{script}", "--json"],
            timeout=600,
            env=env,
        )
        if code != 0 and not payload.get("whatsapp_reply"):
            payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Busqueda LinkedIn fallo: {stderr[-500:]}"}
        payload.setdefault("agent", "jobs")
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
        return

    if MATCH_RE.search(message):
        code, payload, _, stderr = run_json([PY, f"{SCR}/jobs_match.py", "--text", message, "--json"], timeout=180, env=env)
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
