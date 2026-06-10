#!/usr/bin/env python3
"""Lista cron jobs del host (crontab) con descripcion legible."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

# script basename -> (frecuencia legible, descripcion)
KNOWN_JOBS: Dict[str, tuple[str, str]] = {
    "lider_receipts_agent.py": ("Cada 30 min", "Boletas Lider desde Gmail"),
    "run_finanzas_pipeline.sh": ("Cada 15 min", "Pipeline finanzas (merge CSV, etc.)"),
    "gmail_watch_agent.py": ("Cada 15 min", "Watch Gmail (transferencias, etc.)"),
    "support_watch.py": ("Cada 5 min", "Scan logs + auto-fix /supp"),
    "sync-openclaw-models.sh": ("03:17 diario", "Sync modelos OpenClaw"),
    "run-intel-daily-radar-whatsapp.sh": ("08:30 diario", "Radar intel diario"),
    "run-intel-linkedin-scan.sh": ("Cada 12 h", "Scout LinkedIn"),
    "run-intel-consolidated-cron.sh": ("06:15 y 18:15", "Reporte intel consolidado"),
    "run-jobs-daily-auto-whatsapp.sh": ("09:00 diario", "Jobs: buscar + postular 3 vacantes + WhatsApp"),
}

SCRIPT_RE = re.compile(r"([\w.-]+\.(?:py|sh))")
TAG_RE = re.compile(r"#\s*(openclaw-[\w-]+)")


@dataclass
class CronJob:
    schedule: str
    script: str
    label: str
    description: str
    tag: str
    raw: str


def cron_schedule_label(schedule: str) -> str:
    s = schedule.strip()
    for script, (label, _) in KNOWN_JOBS.items():
        if script in s:
            return label
    parts = s.split()
    if len(parts) < 5:
        return s
    minute, hour, dom, month, dow = parts[:5]
    if minute.startswith("*/") and hour == "*" and dom == "*" and month == "*":
        return f"Cada {minute[2:]} min"
    if hour.startswith("*/") and dom == "*" and month == "*":
        return f"Cada {hour[2:]} h"
    if minute != "*" and hour != "*" and dom == "*" and month == "*":
        if "," in hour:
            times = ", ".join(f"{h}:{minute.zfill(2)}" for h in hour.split(","))
            return f"{times} diario"
        return f"{hour}:{minute.zfill(2)} diario"
    return s


def parse_crontab_line(line: str) -> Optional[CronJob]:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    tag_m = TAG_RE.search(line)
    tag = tag_m.group(1) if tag_m else ""
    script_m = SCRIPT_RE.search(line)
    if not script_m:
        return None
    script = script_m.group(1)
    schedule_part = line.split(script)[0].strip()
    # quitar cd/flock/python wrappers del schedule
    tokens = schedule_part.split()
    schedule = " ".join(tokens[:5]) if len(tokens) >= 5 else schedule_part

    label, desc = KNOWN_JOBS.get(script, (cron_schedule_label(schedule), "Job programado"))
    return CronJob(
        schedule=schedule,
        script=script,
        label=label,
        description=desc,
        tag=tag,
        raw=line,
    )


def load_crontab() -> List[str]:
    proc = subprocess.run(["crontab", "-l"], text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        return []
    return proc.stdout.splitlines()


def build_summary(jobs: List[CronJob]) -> str:
    if not jobs:
        return "No hay cron jobs en crontab del usuario actual."

    lines = [f"Cron jobs activos ({len(jobs)}):"]
    for idx, job in enumerate(jobs, start=1):
        lines.append(f"{idx}. *{job.label}*")
        lines.append(f"   {job.script}")
        lines.append(f"   {job.description}")
    lines.append("")
    lines.append("Fuente: crontab -l (host Ubuntu).")
    return "\n".join(lines)


def list_crons() -> dict:
    raw_lines = load_crontab()
    jobs: List[CronJob] = []
    for line in raw_lines:
        job = parse_crontab_line(line)
        if job:
            jobs.append(job)

    summary = build_summary(jobs)
    return {
        "status": "ok",
        "job_count": len(jobs),
        "jobs": [
            {
                "schedule": j.schedule,
                "label": j.label,
                "script": j.script,
                "description": j.description,
                "tag": j.tag,
            }
            for j in jobs
        ],
        "summary": summary,
        "whatsapp_reply": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Lista cron jobs del host.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = list_crons()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["summary"])


if __name__ == "__main__":
    main()
