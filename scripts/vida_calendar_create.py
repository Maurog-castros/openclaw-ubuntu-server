"""Crea eventos en Google Calendar (agente care)."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta

from googleapiclient.discovery import build

from vida_calendar_common import calendar_auth_hint, get_creds
from vida_common import TZ, reply


def build_description(parsed: dict, exams_text: str) -> str:
    lines = []
    if parsed.get("clinical_context"):
        lines.append(f"Motivo: {parsed['clinical_context']}")
    if parsed.get("order_number"):
        lines.append(f"Orden N°: {parsed['order_number']}")
    if parsed.get("order_date"):
        lines.append(f"Fecha orden: {parsed['order_date']}")
    if parsed.get("patient_name"):
        lines.append(f"Paciente: {parsed['patient_name']}")
    lines.append("")
    lines.append("Exámenes solicitados:")
    lines.append(exams_text)
    return "\n".join(lines).strip()


def format_exams_list(exams: list[dict]) -> str:
    lines = []
    for idx, ex in enumerate(exams, start=1):
        code = ex.get("code") or ""
        name = ex.get("name") or "examen"
        details = ex.get("details") or ""
        prefix = f"{idx}. "
        if code:
            prefix += f"({code}) "
        line = prefix + name
        if details:
            line += f" — {details}"
        lines.append(line)
    return "\n".join(lines) if lines else "(sin detalle de exámenes)"


def create_event(
    *,
    title: str,
    date: str,
    time: str,
    location: str,
    description: str,
    duration_min: int = 90,
) -> dict:
    creds = get_creds(write=True)
    if not creds:
        raise RuntimeError(calendar_auth_hint())

    start = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    end = start + timedelta(minutes=duration_min)
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    body = {
        "summary": title,
        "location": location,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": "America/Santiago"},
        "end": {"dateTime": end.isoformat(), "timeZone": "America/Santiago"},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 24 * 60},
                {"method": "popup", "minutes": 60},
            ],
        },
    }
    return service.events().insert(calendarId="primary", body=body).execute()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--location", default="")
    ap.add_argument("--description", default="")
    ap.add_argument("--duration-min", type=int, default=90)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        event = create_event(
            title=args.title,
            date=args.date,
            time=args.time,
            location=args.location,
            description=args.description,
            duration_min=args.duration_min,
        )
        link = event.get("htmlLink", "")
        when = f"{args.date} {args.time}"
        msg = f"*Cita creada en Google Calendar*\n• {args.title}\n• {when}"
        if args.location:
            msg += f"\n• {args.location}"
        if link:
            msg += f"\n• {link}"
        out = reply(msg, event_id=event.get("id"), html_link=link)
    except Exception as exc:
        out = reply(str(exc), status="error")

    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
