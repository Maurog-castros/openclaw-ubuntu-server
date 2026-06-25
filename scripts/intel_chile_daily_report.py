#!/usr/bin/env python3
"""Daily Intelligence Report Chile (formato reports/intelligence) + WhatsApp."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from runtime_paths import repo_root, whatsapp_allow_files

ROOT = repo_root()

OPENCLAW_DIR = ROOT / "openclaw"
COMPOSE = OPENCLAW_DIR / "docker-compose.yml"
COMPOSE_FIN = OPENCLAW_DIR / "docker-compose.finanzas-mounts.yml"
REPORTS_DIR = ROOT / "reports/intelligence"
TARGET_CANDIDATES = list(whatsapp_allow_files())

PROMPT_MORNING = """Genera el Daily Intelligence Report de hoy para Chile (edicion matutina).

Estructura obligatoria en markdown:
# Daily Intelligence Report - Chile
**Fecha:** [dia completo en espanol]
**Analista:** Intel-Agent para Mauro Castro

### 📊 Resumen Ejecutivo
### 🔥 Top 5 Tendencias (Chile)
### 🏢 Impacto para PYMEs Chile
### 📈 Acciones Hoy (Bolsa de Santiago)
### 📚 Fuentes Consultadas

Incluye URLs reales en fuentes. Datos de mercado y tendencias locales cuando puedas.
Espanol chileno tecnico. Sin relleno motivacional."""

PROMPT_EVENING = """Genera el Daily Intelligence Report de hoy para Chile (actualizacion vespertina 19:00).

Misma estructura que la edicion matutina:
# Daily Intelligence Report - Chile
**Fecha:** [dia completo en espanol]
**Analista:** Intel-Agent para Mauro Castro

### 📊 Resumen Ejecutivo
### 🔥 Top 5 Tendencias (Chile)
### 🏢 Impacto para PYMEs Chile
### 📈 Acciones Hoy (Bolsa de Santiago)
### 📚 Fuentes Consultadas

Prioriza novedades de la tarde y cierre de mercado. URLs reales. Espanol chileno."""


def resolve_target_file() -> Path | None:
    for path in TARGET_CANDIDATES:
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return path
    return None


def extract_text(agent_json: dict[str, Any]) -> str:
    for item in agent_json.get("payloads") or []:
        if isinstance(item, dict) and item.get("text"):
            return str(item["text"]).strip()
    return ""


def run_intel_agent(*, message: str, session_key: str, timeout: int = 300) -> tuple[int, dict[str, Any], str]:
    cmd = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE),
        "-f",
        str(COMPOSE_FIN),
        "--project-directory",
        str(OPENCLAW_DIR),
        "exec",
        "-T",
        "openclaw-gateway",
        "openclaw",
        "agent",
        "--local",
        "--agent",
        "intel",
        "--session-key",
        session_key,
        "--message",
        message,
        "--json",
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout, check=False)
    raw = proc.stdout.strip() or proc.stderr.strip()
    payload: dict[str, Any] = {}
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"error": raw[:500]}
    return proc.returncode, payload, raw


def split_for_whatsapp(text: str, limit: int = 3800) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    blocks = re.split(r"(?=^### )", text, flags=re.MULTILINE)
    if len(blocks) <= 1:
        for i in range(0, len(text), limit):
            chunk = text[i : i + limit]
            parts.append(chunk)
        return parts
    current = blocks[0].strip()
    for block in blocks[1:]:
        candidate = (current + "\n\n" + block.strip()).strip() if current else block.strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = block.strip()
    if current:
        parts.append(current)
    return parts or [text[:limit]]


def send_whatsapp(message: str, target_file: Path) -> dict[str, Any]:
    target = target_file.read_text(encoding="utf-8").strip().splitlines()[0]
    proc = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE),
            "-f",
            str(COMPOSE_FIN),
            "--project-directory",
            str(OPENCLAW_DIR),
            "exec",
            "-T",
            "openclaw-gateway",
            "openclaw",
            "message",
            "send",
            "--channel",
            "whatsapp",
            "--target",
            target,
            "--message",
            message,
            "--json",
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    return {"ok": proc.returncode == 0, "stdout": proc.stdout[-600:], "stderr": proc.stderr[-600:]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Intel Daily Chile → archivo + WhatsApp")
    parser.add_argument("--slot", choices=("morning", "evening"), default="morning")
    parser.add_argument("--send-whatsapp", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    today = date.today().isoformat()
    slot = args.slot
    prompt = PROMPT_MORNING if slot == "morning" else PROMPT_EVENING
    session_key = f"agent:intel:chile-daily:{today}:{slot}"

    code, agent_payload, raw = run_intel_agent(message=prompt, session_key=session_key)
    report_text = extract_text(agent_payload)
    if not report_text:
        out = {
            "status": "error",
            "agent": "intel",
            "slot": slot,
            "whatsapp_reply": "No pude generar el reporte Chile hoy.",
            "stderr": raw[-800:],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])
        return 1 if code != 0 else 2

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    dated = REPORTS_DIR / f"{today}-report-{slot}.md"
    latest = REPORTS_DIR / f"{today}-report.md"
    dated.write_text(report_text + "\n", encoding="utf-8")
    latest.write_text(report_text + "\n", encoding="utf-8")
    dated.with_suffix(".md.json").write_text(
        json.dumps(agent_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    payload: dict[str, Any] = {
        "status": "ok",
        "agent": "intel",
        "slot": slot,
        "report_file": str(dated),
        "latest_file": str(latest),
        "whatsapp_reply": f"Intel Daily Chile ({slot}) generado.",
    }

    if args.send_whatsapp:
        target = resolve_target_file()
        if not target:
            payload["status"] = "error"
            payload["whatsapp_reply"] = "Reporte generado pero falta secrets/whatsapp_allow_from.txt"
        else:
            parts = split_for_whatsapp(report_text)
            sent = []
            for index, part in enumerate(parts, start=1):
                header = f"📊 *Intel Daily Chile* ({'mañana' if slot == 'morning' else 'tarde'}"
                if len(parts) > 1:
                    header += f" {index}/{len(parts)}"
                header += ")\n\n"
                sent.append(send_whatsapp(header + part, target))
            payload["message_parts"] = len(parts)
            payload["sent"] = sent
            if not all(item.get("ok") for item in sent):
                payload["status"] = "error"
                payload["whatsapp_reply"] = "Reporte generado; fallo envio WhatsApp."

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload.get("whatsapp_reply", report_text[:200]))
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
