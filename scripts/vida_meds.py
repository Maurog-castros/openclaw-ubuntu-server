"""Recordatorio de medicamentos."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta

from vida_common import DATA, TZ, load_json, now_local, reply


def parse_hhmm(value: str) -> datetime:
    today = now_local().date()
    hh, mm = value.split(":")
    return datetime(today.year, today.month, today.day, int(hh), int(mm), tzinfo=TZ)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    data = load_json(DATA / "medications.json", {"items": []})
    items = data.get("items") or []
    if not items:
        out = reply("No hay medicamentos configurados. Edita data/medications.json.")
    else:
        now = now_local()
        lines = ["*Medicamentos de hoy*"]
        for item in items:
            name = item.get("name", "?")
            dose = item.get("dose", "")
            for sched in item.get("schedule") or []:
                due = parse_hhmm(sched)
                delta = (due - now).total_seconds() / 60
                if -30 <= delta <= 90:
                    status = "⏰ ahora" if abs(delta) <= 15 else ("próximo" if delta > 0 else "pasó hace poco")
                    lines.append(f"• {name} ({dose}) — {sched} ({status})")
                else:
                    lines.append(f"• {name} ({dose}) — {sched}")
        out = reply("\n".join(lines))

    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
