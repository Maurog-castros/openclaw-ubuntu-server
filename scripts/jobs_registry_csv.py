"""Registro CSV de postulaciones Jobs."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jobs_common import JOBS_WS, load_config

CSV_COLUMNS = [
    "applied_at",
    "title",
    "company",
    "job_url",
    "status",
    "cv_file",
    "match_score",
    "questions_answered",
    "notes",
    "grade",
    "recommendation",
    "report_file",
    "source",
    "next_action_at",
]


def csv_path(cfg: dict[str, Any] | None = None) -> Path:
    if JOBS_WS != Path(__file__).resolve().parent.parent / "data/workspace/jobs":
        return JOBS_WS / "applications.csv"
    cfg = cfg or load_config()
    raw = cfg.get("applications_csv") or "data/workspace/jobs/applications.csv"
    p = Path(raw)
    return p if p.is_absolute() else Path(__file__).resolve().parent.parent / raw


def ensure_csv(path: Path | None = None) -> Path:
    path = path or csv_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_COLUMNS).writeheader()
        return path
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
        current = list(rows[0].keys()) if rows else []
        if not current:
            f.seek(0)
            current = next(csv.reader(f), [])
    if current and current != CSV_COLUMNS:
        merged = list(dict.fromkeys(current + CSV_COLUMNS))
        if merged != current:
            tmp = path.with_suffix(path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=merged)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
            tmp.replace(path)
    return path


def append_application(
    *,
    title: str,
    company: str,
    job_url: str,
    status: str,
    cv_file: str = "",
    match_score: int | str = "",
    questions_answered: list[dict[str, str]] | None = None,
    notes: str = "",
    grade: str = "",
    recommendation: str = "",
    report_file: str = "",
    source: str = "",
    next_action_at: str = "",
    cfg: dict[str, Any] | None = None,
) -> dict[str, str]:
    path = ensure_csv(csv_path(cfg))
    with path.open(encoding="utf-8", newline="") as f:
        fieldnames = (csv.DictReader(f).fieldnames or CSV_COLUMNS)
    row = {
        "applied_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "title": title[:200],
        "company": company[:120],
        "job_url": job_url,
        "status": status,
        "cv_file": cv_file,
        "match_score": str(match_score),
        "questions_answered": json.dumps(questions_answered or [], ensure_ascii=False),
        "notes": notes[:500],
        "grade": grade,
        "recommendation": recommendation,
        "report_file": report_file,
        "source": source,
        "next_action_at": next_action_at,
    }
    with path.open("a", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore").writerow(row)
    return row


def list_applications(limit: int = 20, cfg: dict[str, Any] | None = None) -> list[dict[str, str]]:
    path = ensure_csv(csv_path(cfg))
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows[-limit:]


def already_applied(job_url: str, cfg: dict[str, Any] | None = None) -> bool:
    url = (job_url or "").split("?")[0].rstrip("/")
    if not url:
        return False
    for row in list_applications(limit=500, cfg=cfg):
        prev = (row.get("job_url") or "").split("?")[0].rstrip("/")
        if prev == url and row.get("status") in {"applied", "submitted", "ok"}:
            return True
    return False


def format_report_whatsapp(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "📋 *Jobs — sin postulaciones registradas aún.*\nUsa `/jobs postular 1` tras `/jobs vacantes`."
    lines = [f"📋 *Jobs — últimas {len(rows)} postulaciones*", "", "| Fecha | Cargo | Estado |", "|---|---|---|"]
    for row in reversed(rows):
        ts = (row.get("applied_at") or "")[:16].replace("T", " ")
        title = (row.get("title") or "?")[:45]
        status = row.get("status") or "?"
        url = row.get("job_url") or ""
        lines.append(f"• *{ts}* — {title}")
        grade = row.get("grade") or ""
        reco = row.get("recommendation") or ""
        detail = " | ".join(x for x in (status, grade, reco, url[:80]) if x)
        lines.append(f"  {detail}")
    lines += ["", f"_CSV:_ `{csv_path()}`"]
    return "\n".join(lines)
