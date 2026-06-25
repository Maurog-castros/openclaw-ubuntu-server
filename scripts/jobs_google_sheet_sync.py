#!/usr/bin/env python3
"""Sincroniza vacantes Jobs locales hacia Google Sheets Postulaciones."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from jobs_common import JOBS_WS
from jobs_google_sheet_setup import Client, HEADERS, sheets
from jobs_profile import get_profile

VACANCIES = JOBS_WS / "vacancies"
FORMULA_COL = HEADERS.index("dias_sin_movimiento")
STATUS_MAP = {
    "pending_approval": "pendiente_aprobacion",
    "approved": "aprobada",
    "discarded": "retirada",
    "applied": "postulada",
}


def iso_date(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        return match.group(1) if match else ""


def portal_from_url(job_url: str) -> str:
    url = (job_url or "").lower()
    if "linkedin" in url:
        return "linkedin"
    if "chiletrabajos" in url:
        return "chiletrabajos"
    if "laborum" in url:
        return "laborum"
    return "otro"


def modalidad_from_job(job: dict[str, Any]) -> str:
    workplace = str(job.get("workplace") or "").lower()
    location = str(job.get("location") or "").lower()
    if workplace in {"remote", "remoto"} or "remot" in location or "teletrabajo" in location:
        return "remoto"
    if workplace in {"hybrid", "hibrido", "híbrido"} or "hibrid" in location or "híbrid" in location:
        return "hibrido"
    if workplace in {"onsite", "presencial", "on-site", "on_site"} or "presencial" in location:
        return "presencial"
    return "sin_dato"


def sheet_status(job: dict[str, Any]) -> str:
    raw = str(job.get("decision_status") or "")
    if raw in STATUS_MAP:
        return STATUS_MAP[raw]
    if job.get("applied_at"):
        return "postulada"
    if job.get("analyzed_at"):
        return "analizada"
    if job.get("discovered_at"):
        return "descubierta"
    return "descubierta"


def cv_name(path_value: str) -> str:
    if not path_value:
        return ""
    return Path(path_value).name


def load_vacancies() -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for path in sorted(VACANCIES.glob("*/job.json")):
        try:
            jobs.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return sorted(jobs, key=lambda item: float(item.get("vacancy_score") or 0), reverse=True)


def row_from_job(job: dict[str, Any]) -> list[str]:
    best_cv = job.get("best_cv") or {}
    updated = job.get("analyzed_at") or job.get("discovered_at") or ""
    values = [
        str(job.get("job_id") or ""),
        portal_from_url(str(job.get("job_url") or "")),
        str(job.get("company") or ""),
        str(job.get("title") or ""),
        str(job.get("job_url") or ""),
        str(job.get("location") or ""),
        modalidad_from_job(job),
        iso_date(str(job.get("listed_at") or "")),
        iso_date(str(job.get("discovered_at") or "")),
        str(job.get("vacancy_score") or ""),
        str(best_cv.get("file") or ""),
        str(job.get("best_cv_score") or best_cv.get("score") or ""),
        cv_name(str(job.get("generated_cv") or "")),
        sheet_status(job),
        iso_date(str(job.get("applied_at") or "")),
        "no", "", "", "", "no", "", "", "", "sin_definir", "", "",
        "", "media", "", "", "", iso_date(updated),
    ]
    if len(values) != len(HEADERS):
        raise ValueError(f"Fila incompleta: {len(values)} != {len(HEADERS)}")
    return values


def read_existing_ids(client: Client, spreadsheet_id: str) -> dict[str, int]:
    response = client.request(
        "GET",
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/Postulaciones!A2:A1000",
    )
    mapping: dict[str, int] = {}
    for index, row in enumerate(response.get("values") or [], start=2):
        if row and row[0]:
            mapping[str(row[0])] = index
    return mapping


def write_rows(
    client: Client,
    spreadsheet_id: str,
    sheet_id: int,
    start_row: int,
    rows: list[list[str]],
) -> None:
    if not rows:
        return
    left = [row[:FORMULA_COL] for row in rows]
    right = [row[FORMULA_COL + 1:] for row in rows]
    requests_: list[dict[str, Any]] = [
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row - 1,
                    "endRowIndex": start_row - 1 + len(rows),
                    "startColumnIndex": 0,
                    "endColumnIndex": FORMULA_COL,
                },
                "rows": [{"values": [{"userEnteredValue": {"stringValue": value}} for value in row]} for row in left],
                "fields": "userEnteredValue",
            }
        },
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row - 1,
                    "endRowIndex": start_row - 1 + len(rows),
                    "startColumnIndex": FORMULA_COL + 1,
                    "endColumnIndex": len(HEADERS),
                },
                "rows": [{"values": [{"userEnteredValue": {"stringValue": value}} for value in row]} for row in right],
                "fields": "userEnteredValue",
            }
        },
    ]
    client.batch(spreadsheet_id, requests_)


def sync(spreadsheet_id: str) -> dict[str, Any]:
    client = Client()
    metadata = client.metadata(spreadsheet_id)
    sheet_id = sheets(metadata)["Postulaciones"]["properties"]["sheetId"]
    jobs = load_vacancies()
    existing = read_existing_ids(client, spreadsheet_id)
    updates: list[tuple[int, list[str]]] = []
    appends: list[list[str]] = []
    append_start = 0
    next_row = max(existing.values(), default=1) + 1

    for job in jobs:
        row = row_from_job(job)
        job_id = row[0]
        if job_id in existing:
            updates.append((existing[job_id], row))
        else:
            if not appends:
                append_start = next_row
            appends.append(row)
            existing[job_id] = next_row
            next_row += 1

    for start_row, row in updates:
        write_rows(client, spreadsheet_id, sheet_id, start_row, [row])
    if appends:
        write_rows(client, spreadsheet_id, sheet_id, append_start, appends)

    return {
        "status": "ok",
        "spreadsheet_id": spreadsheet_id,
        "vacancies_local": len(jobs),
        "updated": len(updates),
        "appended": len(appends),
        "sheet_rows": len(existing),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spreadsheet-id", default="")
    parser.add_argument("--profile", default="")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    spreadsheet_id = args.spreadsheet_id.strip()
    if not spreadsheet_id:
        profile = get_profile(args.profile or None)
        spreadsheet_id = profile.spreadsheet_id
    if not spreadsheet_id:
        raise ValueError("Falta --spreadsheet-id o spreadsheet_id en config/jobs/profiles.json")

    if not args.apply:
        jobs = load_vacancies()
        print(json.dumps({
            "status": "dry_run",
            "spreadsheet_id": spreadsheet_id,
            "profile": args.profile or get_profile().profile_id,
            "vacancies_local": len(jobs),
            "sample": [row_from_job(jobs[0])[:6] if jobs else []],
        }, ensure_ascii=False, indent=2))
        return
    print(json.dumps(sync(spreadsheet_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
