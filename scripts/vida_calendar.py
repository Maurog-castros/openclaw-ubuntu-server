"""Citas próximas desde Google Calendar."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from vida_calendar_common import calendar_auth_hint, get_creds
from vida_common import reply


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    creds = get_creds(write=False)
    if not creds:
        out = reply(calendar_auth_hint())
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])
        return

    try:
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        end = (datetime.now(UTC) + timedelta(days=args.days)).isoformat().replace("+00:00", "Z")
        events = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                timeMax=end,
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
            .get("items", [])
        )
    except HttpError as exc:
        reason = ""
        try:
            detail = json.loads(exc.content.decode("utf-8"))
            reason = detail.get("error", {}).get("status") or detail.get("error", {}).get("message", "")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            reason = str(exc)
        if "accessNotConfigured" in str(exc) or "SERVICE_DISABLED" in reason:
            out = reply(
                "Fede: Calendar está autenticado, pero la Google Calendar API está deshabilitada "
                "en el proyecto OAuth. Habilítala y reintento."
            )
        else:
            out = reply(f"Fede: no pude leer Calendar ahora ({reason[:120]}).")
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])
        return

    med_kw = ("medico", "médico", "doctor", "clinica", "clínica", "hospital", "dentista", "salud", "examen", "laboratorio")
    lines = ["*Próximas citas*"]
    if not events:
        lines.append("Sin eventos en los próximos días.")
    for ev in events:
        start = ev["start"].get("dateTime", ev["start"].get("date", ""))
        title = ev.get("summary", "(sin título)")
        flag = " 🏥" if any(k in title.lower() for k in med_kw) else ""
        lines.append(f"• {start[:16]} — {title}{flag}")

    out = reply("\n".join(lines))
    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
