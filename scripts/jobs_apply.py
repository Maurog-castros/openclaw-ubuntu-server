#!/usr/bin/env python3
"""Postula a vacantes (LinkedIn Easy Apply) y registra CSV."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

from jobs_common import load_config, parse_vacancy_index, pick_best_cv, resolve_vacancy
from jobs_match import load_cv_index
from jobs_approval import load_job


def parse_indices(text: str) -> list[int]:
    if re.search(r"\bauto\b", text, re.I):
        cfg = load_config()
        n = int(cfg.get("max_auto_apply_per_run") or 3)
        return list(range(1, n + 1))
    m = re.search(r"(?:aplicar|postular|vacante)\s*#?(\d{1,2})\b", text, re.I)
    if m:
        return [int(m.group(1))]
    return []


def run_single(index: int, *, dry_run: bool, headed: bool) -> dict[str, Any]:
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    li_py = root / ".venv-linkedin-intel/bin/python"
    py = str(li_py) if li_py.exists() else "python3"
    cmd = [
        py,
        str(root / "scripts/jobs_linkedin_apply.py"),
        "--index",
        str(index),
        "--json",
    ]
    if dry_run:
        cmd.append("--dry-run")
    if headed:
        cmd.append("--headed")
    proc = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True, timeout=600, check=False)
    if proc.stdout.strip():
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"status": "error", "whatsapp_reply": proc.stdout[:500]}
    return {"status": "error", "whatsapp_reply": (proc.stderr or "Postulacion fallo")[:500]}



def run_job_id(job_id: str, *, dry_run: bool, headed: bool) -> dict[str, Any]:
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    li_py = root / ".venv-linkedin-intel/bin/python"
    py = str(li_py) if li_py.exists() else "python3"
    job = load_job(job_id)
    cmd = [py, str(root / "scripts/jobs_linkedin_apply.py"), "--job-url", job["job_url"], "--json"]
    if dry_run:
        cmd.append("--dry-run")
    if headed:
        cmd.append("--headed")
    proc = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True, timeout=600, check=False)
    if proc.stdout.strip():
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"status": "error", "whatsapp_reply": proc.stdout[:500]}
    return {"status": "error", "whatsapp_reply": (proc.stderr or "Postulacion fallo")[:500]}

def main() -> None:
    parser = argparse.ArgumentParser(description="Postular vacantes LinkedIn")
    parser.add_argument("--text", default="")
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = load_config()
        cv_index = load_cv_index()
        if not cv_index:
            raise RuntimeError("Sin CV indexados. Corre: /jobs indexar cv")

        job_match = re.search(r"\b\d{8,12}\b", args.text)
        if job_match:
            results = [run_job_id(job_match.group(0), dry_run=args.dry_run, headed=args.headed)]
        else:
            results = []
        indices = [] if results else ([args.index] if args.index else parse_indices(args.text))
        if not indices and not results:
            idx = parse_vacancy_index(args.text)
            if idx:
                indices = [idx]
        if not indices and not results:
            raise ValueError("Usa: postular <job_id> tras /jobs aprobar <job_id>")

        for i in indices:
            results.append(run_single(i, dry_run=args.dry_run, headed=args.headed))

        lines = [f"📋 *Jobs — {len(results)} postulacion(es)*", ""]
        for r in results:
            msg = r.get("whatsapp_reply") or r.get("result", {}).get("notes") or str(r.get("status"))
            lines.append(msg)
            lines.append("")

        payload = {
            "status": "ok",
            "agent": "jobs",
            "results": results,
            "whatsapp_reply": "\n".join(lines).strip(),
        }
        if any(r.get("status") == "error" for r in results):
            payload["status"] = "partial"
    except Exception as exc:
        payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Jobs: {exc}"}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload.get("whatsapp_reply", ""))


if __name__ == "__main__":
    main()
