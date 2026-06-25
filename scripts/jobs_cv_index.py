#!/usr/bin/env python3
"""Indexa CVs PDF de runtime/jobs/cv-library para el agente Jobs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from jobs_common import CV_INDEX, JOBS_WS, extract_pdf_text, infer_cv_tags, list_cv_files, load_config


def build_index() -> dict:
    cfg = load_config()
    items = []
    for path in list_cv_files(cfg):
        text = extract_pdf_text(path)
        items.append({
            "filename": path.name,
            "path": str(path),
            "tags": infer_cv_tags(path.name, text),
            "chars": len(text),
            "excerpt": text[:1500],
        })
    from jobs_common import cv_dir as resolve_cv_dir

    return {
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "count": len(items),
        "cv_dir": str(resolve_cv_dir(cfg)),
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Indexar CVs para agente Jobs")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    JOBS_WS.mkdir(parents=True, exist_ok=True)
    payload = build_index()
    CV_INDEX.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [f"CV indexados: {payload['count']}", f"Archivo: {CV_INDEX}"]
    for item in payload["items"][:8]:
        tags = ", ".join(item.get("tags") or [])
        lines.append(f"• {item['filename']} [{tags}]")
    if payload["count"] > 8:
        lines.append(f"… y {payload['count'] - 8} mas")

    result = {
        "status": "ok",
        "agent": "jobs",
        "count": payload["count"],
        "index_file": str(CV_INDEX),
        "whatsapp_reply": "\n".join(lines),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["whatsapp_reply"])


if __name__ == "__main__":
    main()
