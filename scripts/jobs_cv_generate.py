#!/usr/bin/env python3
"""CLI: genera CV ATS (.docx + .pdf) desde vacante pegada."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jobs_cv_builder import generate_cv_files, parse_vacancy, whatsapp_intro


def looks_like_vacancy_paste(text: str) -> bool:
    low = text.lower()
    markers = (
        "requisitos",
        "descripción",
        "description",
        "requirements",
        "full time",
        "presencial",
        "postular",
        "proceso de selección",
        "candidato",
        "vacante",
        "empleo",
    )
    hits = sum(1 for marker in markers if marker in low)
    role_hits = sum(
        1
        for term in (
            "analyst",
            "devops",
            "engineer",
            "developer",
            "architect",
            "sre",
            "data",
            "cloud",
            "analista",
            "ingeniero",
        )
        if term in low
    )
    return len(text) >= 200 and hits >= 2 and role_hits >= 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera CV ATS adaptado a vacante")
    parser.add_argument("--text", default="", help="Texto de vacante pegado")
    parser.add_argument("--text-file", default="", help="Archivo con JD")
    parser.add_argument("--out-dir", default="", help="Directorio de salida")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    else:
        text = args.text or sys.stdin.read()

    text = text.strip()
    if not text:
        payload = {"status": "error", "agent": "jobs", "whatsapp_reply": "Jobs CV: pega la descripción de la vacante."}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["whatsapp_reply"])
        raise SystemExit(1)

    try:
        out_dir = Path(args.out_dir) if args.out_dir else None
        result = generate_cv_files(text, out_dir)
        vacancy = result["vacancy"]
        payload = {
            "status": "ok",
            "agent": "jobs",
            **result,
            "looks_like_vacancy": looks_like_vacancy_paste(text),
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(result["whatsapp_reply"])
    except Exception as exc:
        info = parse_vacancy(text)
        payload = {
            "status": "error",
            "agent": "jobs",
            "whatsapp_reply": f"Jobs CV: no pude generar el archivo ({exc}). Vacante detectada: {info.title} @ {info.company or '?'}.",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["whatsapp_reply"])
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
