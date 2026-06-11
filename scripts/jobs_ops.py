#!/usr/bin/env python3
"""Career-ops style evaluation for /jobs.

Evaluates one pasted job description or a cached match, writes a report, and
tracks the decision without submitting an application.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from jobs_common import (
    JOBS_WS,
    load_config,
    parse_vacancy_index,
    pick_best_cv,
    resolve_vacancy,
    score_vacancy,
    vacancy_title,
)
from jobs_match import load_cv_index
from jobs_registry_csv import append_application, already_applied

STATES = {"evaluated", "applied", "responded", "interview", "offer", "rejected", "discarded", "skip"}

DIMENSIONS = [
    ("role_fit", "Rol objetivo", ("devops", "sre", "cloud", "platform", "mlops", "ai")),
    ("seniority_fit", "Seniority", ("senior", "lead", "principal", "staff", "architect")),
    ("stack_fit", "Stack tecnico", ("kubernetes", "terraform", "aws", "azure", "gcp", "ci/cd", "observability")),
    ("location_fit", "Ubicacion", ("chile", "latam", "remote", "remoto", "santiago", "hybrid", "hibrido")),
    ("application_effort", "Esfuerzo", ("easy apply", "linkedin", "apply", "postula")),
    ("legitimacy", "Legitimidad", ("salary", "equipo", "team", "responsibilities", "responsabilidades", "benefits")),
]

ARCHETYPES = {
    "LLMOps / AI Platform": ("llm", "rag", "mlops", "ai platform", "bedrock", "openai"),
    "SRE / Platform": ("sre", "observability", "reliability", "platform", "incident", "on-call"),
    "Cloud / DevOps": ("devops", "cloud", "kubernetes", "terraform", "ci/cd", "aws", "azure", "gcp"),
    "DevSecOps": ("devsecops", "security", "seguridad", "compliance", "vulnerability"),
    "Technical Lead": ("technical lead", "tech lead", "arquitect", "architect", "lead engineer"),
    "Data / MLOps": ("data engineer", "etl", "pipeline", "mlops", "model"),
}


def clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return re.sub(
        r"^(?:career\s*ops|evaluar|evalua|analiza|analizar|pipeline|oferta|jd)\b\s*[:\-]?\s*",
        "",
        text,
        flags=re.I,
    )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "job")[:70]


def extract_url(text: str) -> str:
    match = re.search(r"https?://\S+", text)
    return match.group(0).rstrip(").,") if match else ""


def extract_company(text: str) -> str:
    patterns = [
        r"\b(?:empresa|company)\s*[:\-]\s*([A-Za-z0-9 .,&_-]{2,80})",
        r"\bat\s+([A-Z][A-Za-z0-9 .,&_-]{2,80})",
        r"\ben\s+([A-Z][A-Za-z0-9 .,&_-]{2,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            company = clean_text(match.group(1))
            company = re.split(
                r"\b(remoto|remote|hibrido|hybrid|presencial|senior|devops|sre|cloud|kubernetes|terraform)\b",
                company,
                flags=re.I,
            )[0]
            return company.strip(" ,.-")[:80]
    return ""


def detect_archetype(text: str) -> str:
    low = text.lower()
    best = ("General", 0)
    for name, terms in ARCHETYPES.items():
        hits = sum(1 for term in terms if term in low)
        if hits > best[1]:
            best = (name, hits)
    return best[0]


def dimension_score(text: str, terms: tuple[str, ...]) -> int:
    low = text.lower()
    hits = sum(1 for term in terms if term in low)
    if hits >= 3:
        return 5
    if hits == 2:
        return 4
    if hits == 1:
        return 3
    return 2


def evaluate_dimensions(text: str) -> list[dict[str, Any]]:
    rows = []
    for key, label, terms in DIMENSIONS:
        score = dimension_score(text, terms)
        rows.append({"key": key, "label": label, "score": score, "weight": 1})
    return rows


def grade_from_score(score: float) -> str:
    if score >= 4.5:
        return "A"
    if score >= 4.0:
        return "B"
    if score >= 3.25:
        return "C"
    if score >= 2.5:
        return "D"
    return "F"


def recommendation(grade: str, duplicate: bool) -> str:
    if duplicate:
        return "monitor"
    if grade in {"A", "B"}:
        return "apply"
    if grade == "C":
        return "monitor"
    return "skip"


def status_for_recommendation(value: str) -> str:
    return "evaluated" if value in {"apply", "monitor"} else "skip"


def next_action(value: str) -> str:
    if value == "apply":
        return datetime.now().astimezone().isoformat(timespec="seconds")
    if value == "monitor":
        return (datetime.now().astimezone() + timedelta(days=3)).isoformat(timespec="seconds")
    return ""


def load_vacancy(text: str) -> dict[str, Any]:
    index = parse_vacancy_index(text)
    try:
        if index:
            return resolve_vacancy(text, index)
    except ValueError:
        pass
    return {"source": "manual", "text": text, "url": extract_url(text), "match_score": 0}


def write_report(data: dict[str, Any]) -> Path:
    reports = JOBS_WS / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    slug = slugify(f"{data['company'] or 'unknown'}-{data['title']}")
    path = reports / f"{today}-{slug}.md"
    dimensions = "\n".join(
        f"| {row['label']} | {row['score']}/5 |" for row in data["dimensions"]
    )
    gaps = "\n".join(f"- {gap}" for gap in data["gaps"]) or "- Sin brechas duras detectadas por reglas locales."
    content = f"""# {data['title']}

Fecha: {today}
Empresa: {data['company'] or 'No detectada'}
URL: {data['url'] or 'No disponible'}
Estado: {data['status']}
Recomendacion: {data['recommendation']}
Nota: {data['grade']} ({data['average_score']:.2f}/5)
Arquetipo: {data['archetype']}
CV recomendado: {data['cv_file'] or 'CV general'}

## Evaluacion A-F

| Dimension | Score |
|---|---:|
{dimensions}

## Resumen

{data['summary']}

## Brechas / mitigacion

{gaps}

## Estrategia

- Si decides aplicar: usa `/jobs postular {data['index_hint']}` si viene de la lista de matches.
- Si es manual: prepara CV `{data['cv_file'] or 'general'}` y carta corta orientada al arquetipo `{data['archetype']}`.
- No se envio postulacion desde esta evaluacion.

## Texto base

```text
{data['text'][:4000]}
```
"""
    path.write_text(content, encoding="utf-8")
    return path


def build_evaluation(text: str) -> dict[str, Any]:
    cfg = load_config()
    vacancy = load_vacancy(text)
    body = clean_text(vacancy.get("text") or text)
    url = vacancy.get("url") or extract_url(text)
    title = vacancy_title(body) or "Oferta laboral"
    company = extract_company(body)
    cv = pick_best_cv(body, load_cv_index())
    dimensions = evaluate_dimensions(body)
    base = score_vacancy(body, cfg)
    average = sum(row["score"] * row["weight"] for row in dimensions) / sum(row["weight"] for row in dimensions)
    if base >= int(cfg.get("min_match_score") or 12):
        average = min(5.0, average + 0.35)
    grade = grade_from_score(average)
    duplicate = already_applied(url, cfg) if url else False
    reco = recommendation(grade, duplicate)
    status = status_for_recommendation(reco)
    gaps = []
    low = body.lower()
    if not any(term in low for term in ("salary", "sueldo", "renta", "compensation")):
        gaps.append("No aparece rango salarial; investigar antes de invertir mucho tiempo.")
    if not any(term in low for term in ("remote", "remoto", "hybrid", "hibrido", "santiago", "chile", "latam")):
        gaps.append("Ubicacion/modalidad poco clara; confirmar remoto o Chile/LATAM.")
    if duplicate:
        gaps.append("URL ya figura como postulada; evitar duplicar aplicacion.")
    return {
        "title": title,
        "company": company,
        "url": url,
        "text": body,
        "source": vacancy.get("source") or "manual",
        "match_score": base or vacancy.get("match_score") or "",
        "cv_file": cv.get("filename") if cv else "",
        "dimensions": dimensions,
        "average_score": average,
        "grade": grade,
        "recommendation": reco,
        "status": status,
        "archetype": detect_archetype(body),
        "gaps": gaps,
        "summary": f"{title}. Fit {grade}; recomendacion: {reco}.",
        "index_hint": parse_vacancy_index(text) or "",
    }


def format_whatsapp(data: dict[str, Any], report: Path) -> str:
    lines = [
        f"Jobs Ops: {data['grade']} ({data['average_score']:.2f}/5) — {data['recommendation']}",
        f"{data['title'][:90]}",
        f"CV: {data['cv_file'] or 'general'} | {data['archetype']}",
    ]
    if data["gaps"]:
        lines.append(f"Riesgo: {data['gaps'][0]}")
    lines.append(f"Reporte: {report}")
    if data["recommendation"] == "apply" and data["index_hint"]:
        lines.append(f"Siguiente: /jobs postular {data['index_hint']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate job as career-ops pipeline")
    parser.add_argument("--text", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        data = build_evaluation(args.text)
        report = write_report(data)
        row = append_application(
            title=data["title"],
            company=data["company"],
            job_url=data["url"],
            status=data["status"],
            cv_file=data["cv_file"],
            match_score=data["match_score"],
            notes=data["summary"],
            grade=data["grade"],
            recommendation=data["recommendation"],
            report_file=str(report),
            source=data["source"],
            next_action_at=next_action(data["recommendation"]),
        )
        payload = {
            "status": "ok",
            "agent": "jobs",
            "evaluation": data,
            "tracker_row": row,
            "report_file": str(report),
            "whatsapp_reply": format_whatsapp(data, report),
        }
    except Exception as exc:
        payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Jobs Ops: {exc}"}

    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["whatsapp_reply"])


if __name__ == "__main__":
    main()
