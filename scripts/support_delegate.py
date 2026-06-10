#!/usr/bin/env python3
"""Delegate /supp — soporte tecnico OpenClaw."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent

SCR = ROOT / "scripts"
if str(SCR) not in sys.path:
    sys.path.insert(0, str(SCR))

from support_common import live_health
from whatsapp_menu import finish_reply, resolve_menu_choice

LOGS_RE = re.compile(r"\b(logs?|ultim(?:os|as)|escanear|revisar)\b", re.I)
ESTADO_RE = re.compile(r"\b(estado\s+sistema|estado\s+del\s+sistema|system\s+status)\b", re.I)
CRON_RE = re.compile(r"\b(cron\s*jobs?|crons?|listar\s+cron|tareas\s+programad)\b", re.I)

RUN_PY = SCR / "run-finanzas-py.sh"
SUPP_PREFIX_RE = re.compile(r"^\s*/supp\b", re.I)


def py_cmd(script: str, *args: str) -> list[str]:
    return [str(RUN_PY), str(SCR / script), *args]


def run_json(cmd: list[str], timeout: int = 180) -> dict:
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout, check=False)
    if proc.stdout.strip():
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"whatsapp_reply": proc.stdout.strip()}
    return {"status": "error", "message": (proc.stderr or proc.stdout)[:800]}


def strip_prefix(text: str) -> str:
    return SUPP_PREFIX_RE.sub("", text or "").strip()


def cmd_status() -> dict:
    health = live_health()
    lines = [
        "🛠 *Supp — status*",
        f"Gateway: {'OK' if health.get('gateway_healthy') else 'NO healthy'}",
        f"WhatsApp pending: {health.get('whatsapp_pending', 0)}",
        f"Sesion /fin: {health.get('fin_session', {}).get('status', '?')}",
        f"Entregas failed fin: {health.get('fin_failed_deliveries', 0)}",
    ]
    if health.get("needs_remediation"):
        lines.append("*Sistema fin necesita auto-fix (menu 2)*")
    else:
        lines.append("Sistema fin OK en vivo.")

    rows = []
    try:
        import csv

        csv_path = ROOT / "data/support_findings.csv"
        if csv_path.exists():
            with csv_path.open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))[-5:]
    except Exception:
        pass
    if rows:
        lines.append("")
        lines.append("*Historial CSV (ultimos intentos):*")
        for r in reversed(rows):
            st = r.get("status") or "?"
            note = " (reintentable con menu 2)" if st == "failed" else ""
            lines.append(
                f"• {r.get('detected_at', '')[:16]} [{st}]{note} "
                f"{r.get('category')}: {r.get('summary', '')[:45]}"
            )
    summary = "\n".join(lines)
    return {"status": "ok", "summary": summary, "whatsapp_reply": summary}


def dispatch_supp(text: str) -> dict:
    lower = text.lower()

    if not text or lower in {"status", "estado", "help", "ayuda"} or ESTADO_RE.search(text):
        return cmd_status()
    if lower in {"cron", "crons", "cronjobs"} or CRON_RE.search(text):
        result = run_json(py_cmd("support_list_crons.py", "--json"))
        result.setdefault("whatsapp_reply", result.get("summary", ""))
        return result
    if lower in {"scan", "escanear", "revisar", "logs"} or LOGS_RE.search(text):
        result = run_json(py_cmd("support_scan_logs.py", "--json"))
        result.setdefault("whatsapp_reply", result.get("summary", ""))
        return result
    if lower.split()[0] in {"fix", "arregla", "remedia", "soluciona"} or lower == "fix":
        scan = run_json(py_cmd("support_scan_logs.py", "--json"))
        fix = run_json(py_cmd("support_remediate.py", "--auto", "--json"))
        reply = fix.get("whatsapp_reply") or fix.get("summary", "")
        if scan.get("summary"):
            reply = f"{scan.get('summary', '')}\n\n───\n{reply}"
        return {"status": fix.get("status", "ok"), "whatsapp_reply": reply}
    if lower.startswith("ultimos"):
        return cmd_status()

    result = run_json(py_cmd("support_scan_logs.py", "--json"))
    if result.get("open_findings", 0) > 0:
        fix = run_json(py_cmd("support_remediate.py", "--auto", "--json"))
        return {
            "status": "ok",
            "whatsapp_reply": (
                f"🛠 *Supp*\n{result.get('summary', '')}\n\n"
                f"───\n{fix.get('whatsapp_reply', fix.get('summary', ''))}"
            ),
        }
    result["whatsapp_reply"] = f"🛠 *Supp*\n{result.get('summary', 'Todo OK')}"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Delegate /supp")
    parser.add_argument("--text", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    text = strip_prefix(args.text)

    menu_opt = resolve_menu_choice(text)
    if menu_opt:
        from finanzas_delegate import run_menu_option as fin_run_menu

        result = fin_run_menu(menu_opt)
    else:
        result = dispatch_supp(text)

    result.setdefault("agent", "supp")
    reply = result.get("whatsapp_reply") or result.get("summary") or ""
    if reply:
        result["whatsapp_reply"] = finish_reply(reply, agent="supp")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("whatsapp_reply", ""))


if __name__ == "__main__":
    main()
