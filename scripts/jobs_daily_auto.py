#!/usr/bin/env python3
"""Cron diario: buscar vacantes LinkedIn, postular auto (3) y avisar por WhatsApp."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from jobs_common import ROOT, load_config
from jobs_registry_csv import csv_path, list_applications
from runtime_paths import whatsapp_allow_files

FIN_PY = ROOT / ".venv-finanzas/bin/python"
LI_PY = ROOT / ".venv-linkedin-intel/bin/python"
OPENCLAW_DIR = ROOT / "openclaw"
TARGET_CANDIDATES = list(whatsapp_allow_files())


def run_script(py: Path, script: str, *args: str, timeout: int = 900) -> dict[str, Any]:
    cmd = [str(py if py.exists() else "python3"), str(ROOT / "scripts" / script), *args]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout, check=False)
    if proc.stdout.strip():
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"status": "error", "message": proc.stdout[:500], "stderr": proc.stderr[-500:]}
    return {"status": "error", "message": (proc.stderr or proc.stdout or "sin salida")[:500]}


def resolve_target_file() -> Path | None:
    for path in TARGET_CANDIDATES:
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return path
    return None


def send_whatsapp(message: str, target_file: Path) -> dict[str, Any]:
    target = target_file.read_text(encoding="utf-8").strip().splitlines()[0]
    if len(message) > 3800:
        message = message[:3700].rstrip() + "\n\n(Truncado; ver CSV local.)"
    cmd = [
        "docker", "compose", "-f", "docker-compose.yml",
        "-f", "docker-compose.finanzas-mounts.yml",
        "exec", "-T", "openclaw-gateway",
        "openclaw", "message", "send",
        "--channel", "whatsapp",
        "--target", target,
        "--message", message,
        "--json",
    ]
    proc = subprocess.run(cmd, cwd=str(OPENCLAW_DIR), text=True, capture_output=True, timeout=120, check=False)
    return {"ok": proc.returncode == 0, "stdout": proc.stdout[-600:], "stderr": proc.stderr[-600:]}


def applications_today() -> list[dict[str, str]]:
    today = date.today().isoformat()
    return [r for r in list_applications(50) if (r.get("applied_at") or "").startswith(today)]


def build_summary(
    *,
    search: dict[str, Any],
    apply: dict[str, Any],
    today_rows: list[dict[str, str]],
) -> str:
    found = int(search.get("count") or len(search.get("vacancies") or []))
    results = apply.get("results") or []
    applied = failed = skipped = 0
    for r in results:
        st = (r.get("result") or {}).get("status") or r.get("status") or ""
        if st == "applied":
            applied += 1
        elif st == "skipped":
            skipped += 1
        elif st in {"failed", "error"}:
            failed += 1

    lines = [
        f"📋 *Jobs Daily Auto — {date.today().isoformat()}*",
        "",
        f"🔎 Vacantes encontradas: *{found}*",
        f"✅ Postulaciones enviadas: *{applied}*",
        f"⚠️ Fallidas: *{failed}*",
        f"⏭️ Omitidas (ya en CSV): *{skipped}*",
        "",
    ]

    if today_rows:
        lines.append("*Registro de hoy:*")
        for row in reversed(today_rows[-5:]):
            ts = (row.get("applied_at") or "")[:16].replace("T", " ")
            title = (row.get("title") or "?")[:50]
            status = row.get("status") or "?"
            url = row.get("job_url") or ""
            lines.append(f"• {ts} — *{title}* ({status})")
            if url:
                lines.append(f"  {url}")
    elif found == 0:
        lines.append("_Sin vacantes nuevas con match hoy._")
    else:
        lines.append("_Sin postulaciones nuevas registradas hoy (revisar logs)._")

    lines += ["", f"_CSV:_ `{csv_path()}`"]
    if apply.get("status") == "error":
        lines.append(f"_Error apply:_ {apply.get('whatsapp_reply', '')[:200]}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Jobs daily: buscar + postular + WhatsApp")
    parser.add_argument("--send-whatsapp", action="store_true")
    parser.add_argument("--skip-apply", action="store_true", help="Solo buscar (debug)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    payload: dict[str, Any] = {"status": "ok", "agent": "jobs", "steps": {}}

    try:
        index_res = run_script(FIN_PY, "jobs_cv_index.py", "--json", timeout=120)
        payload["steps"]["index_cv"] = index_res

        search_res = run_script(LI_PY, "jobs_linkedin_search.py", "--json", timeout=600)
        payload["steps"]["search"] = search_res
        found = int(search_res.get("count") or 0)

        apply_res: dict[str, Any] = {"status": "skip", "results": []}
        if not args.skip_apply and found > 0:
            n = int(cfg.get("max_auto_apply_per_run") or 3)
            apply_res = run_script(
                FIN_PY,
                "jobs_apply.py",
                "--text",
                "postular auto",
                "--json",
                timeout=1800,
            )
        payload["steps"]["apply"] = apply_res

        today_rows = applications_today()
        summary = build_summary(search=search_res, apply=apply_res, today_rows=today_rows)
        payload["whatsapp_reply"] = summary
        payload["applications_today"] = today_rows

        if args.send_whatsapp:
            target = resolve_target_file()
            if not target:
                payload["sent"] = {"ok": False, "reason": "missing whatsapp_allow_from.txt"}
                payload["status"] = "error"
                payload["whatsapp_reply"] += "\n\n⚠️ No pude enviar WhatsApp: falta secrets/whatsapp_allow_from.txt"
            else:
                payload["sent"] = send_whatsapp(summary, target)
                if not payload["sent"].get("ok"):
                    payload["status"] = "partial"

    except Exception as exc:
        payload = {
            "status": "error",
            "agent": "jobs",
            "whatsapp_reply": f"📋 Jobs Daily Auto fallo: {exc}",
        }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload.get("whatsapp_reply", ""))


if __name__ == "__main__":
    main()
