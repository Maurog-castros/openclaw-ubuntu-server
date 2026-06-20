#!/usr/bin/env python3
"""Construye perfil Laborum estructurado desde CV DOCX."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from jobs_common import JOBS_WS
from runtime_paths import cv_library_dir

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}
DATE_RE = re.compile(
    r"(?P<start_month>" + "|".join(MONTHS) + r")\s+(?P<start_year>\d{4})"
    r"\s*[–-]\s*(?:(?P<end_month>" + "|".join(MONTHS) + r")\s+"
    r"(?P<end_year>\d{4})|(?P<present>actualidad|presente))",
    re.I,
)
OUTPUT_DIR = JOBS_WS / "laborum"


def docx_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    return [
        "".join(node.text or "" for node in paragraph.findall(".//w:t", NS)).strip()
        for paragraph in root.findall(".//w:p", NS)
    ]


def newest_cv() -> Path:
    candidates = list(cv_library_dir().glob("*.docx"))
    if not candidates:
        raise FileNotFoundError("No hay CV DOCX en runtime/jobs/cv-library.")
    return max(candidates, key=lambda item: item.stat().st_mtime)


def subarea_for(role: str) -> str:
    low = role.lower()
    if any(term in low for term in ("system", "infra", "cloud", "devops", "platform")):
        return "Infraestructura"
    return "Programación"


def parse_experiences(path: Path) -> list[dict[str, Any]]:
    paragraphs = docx_paragraphs(path)
    try:
        start = paragraphs.index("EXPERIENCIA PROFESIONAL") + 1
    except ValueError as exc:
        raise ValueError("CV sin sección EXPERIENCIA PROFESIONAL.") from exc
    end = next((i for i in range(start, len(paragraphs)) if paragraphs[i] == "LOGROS CLAVE"), len(paragraphs))
    experiences: list[dict[str, Any]] = []
    index = start
    while index + 1 < end:
        company, role_line = paragraphs[index], paragraphs[index + 1]
        match = DATE_RE.search(role_line)
        if not company or not match:
            index += 1
            continue
        role = role_line[: match.start()].strip()
        next_index = index + 2
        while next_index + 1 < end and not DATE_RE.search(paragraphs[next_index + 1]):
            next_index += 1
        details = [
            text for text in paragraphs[index + 2 : next_index]
            if text and text not in {"Responsabilidades principales:", "Logros destacados:"}
        ]
        description = " ".join(details)
        if len(description) > 1000:
            description = description[:997].rsplit(" ", 1)[0] + "..."
        payload = {
            "company": company,
            "company_activity": "Informática / Tecnología",
            "role": role,
            "experience_level": "Senior",
            "area": "Tecnología, Sistemas y Telecomunicaciones",
            "subarea": subarea_for(role),
            "country": "Chile",
            "start_month": MONTHS[match.group("start_month").lower()],
            "start_year": int(match.group("start_year")),
            "end_month": MONTHS.get((match.group("end_month") or "").lower()),
            "end_year": int(match.group("end_year")) if match.group("end_year") else None,
            "current": bool(match.group("present")),
            "description": description,
            "people_managed": 0,
            "managed_budget": False,
        }
        identity = f"{company}|{role}|{payload['start_year']}|{payload['start_month']}"
        payload["key"] = hashlib.sha256(identity.lower().encode()).hexdigest()[:16]
        experiences.append(payload)
        index = next_index
    if not experiences:
        raise ValueError("No pude extraer experiencias del CV.")
    return experiences


def build_profile(cv_path: Path | None = None) -> dict[str, Any]:
    cv_path = cv_path or newest_cv()
    experiences = parse_experiences(cv_path)
    return {
        "source_cv": str(cv_path),
        "source_mtime": datetime.fromtimestamp(cv_path.stat().st_mtime).astimezone().isoformat(),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "experience_count": len(experiences),
        "experiences": experiences,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="CV DOCX a perfil Laborum")
    parser.add_argument("--cv", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    profile = build_profile(Path(args.cv) if args.cv else None)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / "profile.json"
    output.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {
        "status": "ok",
        "agent": "jobs",
        "profile_file": str(output),
        "source_cv": profile["source_cv"],
        "experience_count": profile["experience_count"],
        "whatsapp_reply": f"Laborum: {profile['experience_count']} experiencias extraídas. Preview: /jobs laborum preview",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["whatsapp_reply"])


if __name__ == "__main__":
    main()
