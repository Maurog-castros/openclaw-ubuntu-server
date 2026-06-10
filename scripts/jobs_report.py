#!/usr/bin/env python3
"""Informe de postulaciones registradas en CSV."""

from __future__ import annotations

import argparse
import json

from jobs_registry_csv import format_report_whatsapp, list_applications


def main() -> None:
    parser = argparse.ArgumentParser(description="Reporte postulaciones CSV")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = list_applications(limit=args.limit)
    payload = {
        "status": "ok",
        "agent": "jobs",
        "count": len(rows),
        "applications": rows,
        "whatsapp_reply": format_report_whatsapp(rows),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["whatsapp_reply"])


if __name__ == "__main__":
    main()
