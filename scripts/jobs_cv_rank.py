#!/usr/bin/env python3
"""Rankea CVs contra una vacante y genera CV adaptado si falta fit."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from jobs_common import JOBS_WS, cv_dir, extract_pdf_text, list_cv_files, load_config

DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

KEYWORD_WEIGHTS = {
    "aws": 1.6,
    "eks": 1.4,
    "ecs": 1.3,
    "lambda": 1.2,
    "cloudformation": 1.2,
    "cdk": 1.1,
    "vpc": 1.0,
    "iam": 1.2,
    "s3": 0.8,
    "cloudwatch": 1.1,
    "rds": 1.0,
    "documentdb": 1.0,
    "docker": 1.3,
    "kubernetes": 1.6,
    "helm": 1.0,
    "terraform": 1.5,
    "iac": 1.1,
    "github actions": 1.3,
    "jenkins": 1.0,
    "ci/cd": 1.4,
    "gitops": 1.2,
    "observability": 1.4,
    "prometheus": 1.0,
    "grafana": 1.0,
    "datadog": 0.9,
    "finops": 1.4,
    "cost": 0.8,
    "security": 1.0,
    "secrets": 0.8,
    "linux": 1.1,
    "python": 0.9,
    "bash": 0.8,
    "financial": 1.2,
    "fintech": 1.0,
    "regulated": 1.0,
    "resilience": 1.0,
    "availability": 1.0,
    "incident": 0.9,
    "apigee": 1.6, "api": 1.0, "microservices": 1.3, "microservicios": 1.3,
    "node.js": 1.2, "typescript": 1.1, "angular": 1.0, ".net": 1.2,
    "c#": 1.1, "java": 1.0, "kotlin": 1.0, "gcp": 1.2,
    "sql": 1.2, "etl": 1.4, "data engineer": 1.6, "big data": 1.2,
    "cybersecurity": 1.5, "ciberseguridad": 1.5, "pentesting": 1.6,
    "devsecops": 1.3, "architecture": 1.1, "arquitectura": 1.1,
    "ddd": 1.2, "rest": 1.0, "integration": 1.1, "integración": 1.1, "sap": 1.0,
}

GENERIC_STOPWORDS = {
    "para",
    "con",
    "como",
    "los",
    "las",
    "una",
    "uno",
    "que",
    "por",
    "del",
    "and",
    "the",
    "and",
    "you",
    "our",
    "sus",
    "mas",
    "muy",
    "sin",
    "ser",
    "son",
    "this",
}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "job")[:80]


def extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    parts: list[str] = []
    for node in root.findall(".//w:t", DOCX_NS):
        if node.text:
            parts.append(node.text)
    return clean_text(" ".join(parts))


def extract_cv_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            return extract_pdf_text(path)
        except RuntimeError:
            import subprocess
            proc = subprocess.run(["pdftotext", str(path), "-"], text=True, capture_output=True, timeout=60, check=False)
            return clean_text(proc.stdout)
    if path.suffix.lower() == ".docx":
        return extract_docx_text(path)
    return ""


def list_all_cv_files() -> list[Path]:
    cfg = load_config()
    base = cv_dir(cfg)
    excludes = [x.lower() for x in (cfg.get("cv_exclude_patterns") or [])]
    out: list[Path] = []
    for path in sorted(base.glob("*")):
        if path.suffix.lower() not in {".pdf", ".docx"}:
            continue
        if any(ex in path.name.lower() for ex in excludes):
            continue
        out.append(path)
    if out:
        return out
    return list_cv_files(cfg)


def infer_role(job_text: str) -> str:
    low = job_text.lower()
    if "data engineer" in low or "ingeniería de datos" in low:
        return "Senior Data Engineer"
    if "ciberseguridad" in low or "cybersecurity" in low or "pentesting" in low:
        return "Senior DevSecOps / Cybersecurity Engineer"
    if "apigee" in low or "arquitecturas de integración" in low:
        return "Technical Lead - API Integration"
    if "líder técnico" in low or "technical lead" in low:
        return "Senior Technical Lead"
    if "ingeniero de software" in low or "software engineer" in low:
        return "Senior Software Engineer"
    if "cloud engineer" in low:
        return "Senior AWS Cloud Engineer"
    if "sre" in low:
        return "Senior SRE / Platform Engineer"
    if "devops" in low:
        return "Senior DevOps Engineer"
    return "Senior Cloud / DevOps Engineer"


def infer_company(job_text: str) -> str:
    if "creditú" in job_text.lower() or "creditu" in job_text.lower():
        return "Creditu"
    patterns = [
        r"\b(?:en|at)\s+([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9 .&-]{2,60})",
        r"únete\s+a\s+([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9 .&-]{2,60})",
        r"como\s+nuestro.*?\s+([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9 .&-]{2,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, job_text, re.I)
        if match:
            value = clean_text(match.group(1)).strip(" .,-")
            value = re.split(r"\b(como|buscamos|que|en|somos)\b", value, flags=re.I)[0].strip()
            if 2 <= len(value) <= 60:
                return value
    return "target-company"


def job_keywords(job_text: str) -> list[str]:
    low = job_text.lower()
    found = [kw for kw in KEYWORD_WEIGHTS if kw in low]
    tokens = re.findall(r"[a-záéíóúñ0-9+#./-]{4,}", low)
    counts = Counter(t for t in tokens if t not in GENERIC_STOPWORDS)
    for token, _ in counts.most_common(20):
        if token not in found and any(x in token for x in ("aws", "cloud", "devops", "kuber", "terra", "finop")):
            found.append(token)
    return found


def score_cv(cv_text: str, job_text: str) -> dict[str, Any]:
    low = cv_text.lower()
    kws = job_keywords(job_text)
    total = sum(KEYWORD_WEIGHTS.get(kw, 0.7) for kw in kws) or 1.0
    hits = [kw for kw in kws if kw in low]
    hit_score = sum(KEYWORD_WEIGHTS.get(kw, 0.7) for kw in hits)
    score = min(10.0, 10.0 * hit_score / total)
    # 9.5+ requires broad evidence, not perfect overlap on a tiny keyword set.
    if len(kws) < 12 or len(hits) < 12:
        score = min(score, 9.4)
    missing = [kw for kw in kws if kw not in hits]
    return {
        "score": round(score, 2),
        "matched_keywords": hits,
        "missing_keywords": missing[:18],
    }


def rank_cvs(job_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in list_all_cv_files():
        try:
            text = extract_cv_text(path)
        except Exception as exc:
            rows.append({"file": path.name, "path": str(path), "score": 0.0, "error": str(exc)})
            continue
        scored = score_cv(text, job_text)
        rows.append(
            {
                "file": path.name,
                "path": str(path),
                "score": scored["score"],
                "matched_keywords": "; ".join(scored["matched_keywords"]),
                "missing_keywords": "; ".join(scored["missing_keywords"]),
                "chars": len(text),
            }
        )
    rows.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
    return rows


def write_ranking_csv(rows: list[dict[str, Any]], out_dir: Path, slug: str) -> Path:
    path = out_dir / f"{slug}-cv-ranking.csv"
    cols = ["file", "score", "matched_keywords", "missing_keywords", "path", "chars", "error"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def paragraph_xml(text: str, *, bold: bool = False, size: int = 22, style: str = "") -> str:
    ppr = f"<w:pPr><w:pStyle w:val=\"{style}\"/></w:pPr>" if style else ""
    b = "<w:b/>" if bold else ""
    return (
        f"<w:p>{ppr}<w:r><w:rPr>{b}<w:sz w:val=\"{size}\"/></w:rPr>"
        f"<w:t>{html.escape(text)}</w:t></w:r></w:p>"
    )


def bullet_xml(text: str) -> str:
    return paragraph_xml(f"- {text}", size=21)


def minimal_docx(path: Path, paragraphs: list[str]) -> None:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(paragraphs)
        + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        + "</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)


def generate_adapted_cv(job_text: str, out_dir: Path, slug: str) -> Path:
    from jobs_cv_builder import build_docx, parse_vacancy

    vacancy = parse_vacancy(job_text)
    path = out_dir / f"CV_Mauricio_Castro_{slug}.docx"
    build_docx(vacancy, path)
    return path


def write_report(rows: list[dict[str, Any]], job_text: str, csv_path: Path, cv_path: Path | None, out_dir: Path, slug: str) -> Path:
    path = out_dir / f"{slug}-analysis.md"
    best = rows[0] if rows else {}
    lines = [
        f"# Analisis CV vs vacante - {slug}",
        "",
        f"Fecha: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"CSV ranking: {csv_path}",
        f"Mejor CV existente: {best.get('file', 'sin dato')}",
        f"Nota mejor CV: {best.get('score', 0)}/10",
        f"CV generado: {cv_path or 'No generado'}",
        "",
        "## Top CVs",
        "",
    ]
    for i, row in enumerate(rows[:8], 1):
        lines.append(f"{i}. {row.get('file')} - {row.get('score')}/10")
        lines.append(f"   Match: {row.get('matched_keywords', '')}")
        if row.get("missing_keywords"):
            lines.append(f"   Falta: {row.get('missing_keywords')}")
    lines += ["", "## Vacante base", "", "```text", job_text[:5000], "```"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank CVs contra vacante y genera CV adaptado")
    parser.add_argument("--text-file", required=True)
    parser.add_argument("--threshold", type=float, default=9.5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    job_path = Path(args.text_file)
    job_text = job_path.read_text(encoding="utf-8")
    stamp = datetime.now().strftime("%Y-%m-%d")
    slug = f"{stamp}-{slugify(infer_company(job_text) + '-' + infer_role(job_text))}"
    out_dir = JOBS_WS / "cv_rankings"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = rank_cvs(job_text)
    ranking_csv = write_ranking_csv(rows, out_dir, slug)
    best_score = float(rows[0]["score"]) if rows else 0.0
    generated_cv = generate_adapted_cv(job_text, out_dir, slug) if best_score < args.threshold else None
    report = write_report(rows, job_text, ranking_csv, generated_cv, out_dir, slug)
    payload = {
        "status": "ok",
        "agent": "jobs",
        "ranking_csv": str(ranking_csv),
        "analysis_report": str(report),
        "generated_cv": str(generated_cv) if generated_cv else "",
        "best_score": best_score,
        "best_cv": rows[0] if rows else {},
        "top": rows[:8],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else str(report))


if __name__ == "__main__":
    main()
