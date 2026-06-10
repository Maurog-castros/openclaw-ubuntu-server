"""Resumen compacto desde reportes Intel para armar publicaciones."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import resolve_data_path

DEFAULT_INTEL_REPORTS = "data/workspace/marketing/intel/reports"
DEFAULT_INTEL_LEADS = "data/workspace/marketing/intel/leads/leads.md"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def tokenize_topic(topic: str) -> List[str]:
    words = re.findall(r"[a-z0-9áéíóúñ]+", topic.lower())
    stop = {"de", "la", "el", "en", "un", "una", "para", "con", "los", "las", "del", "al", "y", "o"}
    return [w for w in words if len(w) > 2 and w not in stop]


def score_text(text: str, tokens: List[str]) -> int:
    lowered = text.lower()
    return sum(1 for t in tokens if t in lowered)


def load_report_snippets(reports_dir: Path, topic: str, max_files: int = 5) -> List[dict]:
    tokens = tokenize_topic(topic)
    if not reports_dir.exists():
        return []
    files = sorted(reports_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    scored: List[tuple[int, Path, str]] = []
    for path in files[:30]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        score = score_text(text, tokens) if tokens else 1
        scored.append((score, path, text))
    scored.sort(key=lambda x: (x[0], x[1].stat().st_mtime), reverse=True)
    out: List[dict] = []
    for score, path, text in scored[:max_files]:
        if tokens and score == 0:
            continue
        lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        bullets = [ln for ln in lines if ln.startswith(("-", "*", "•"))][:8]
        if not bullets:
            bullets = lines[:6]
        out.append(
            {
                "file": str(path.name),
                "score": score,
                "bullets": bullets[:8],
            }
        )
    return out


def load_leads_snippet(leads_path: Path, topic: str, max_lines: int = 8) -> List[str]:
    if not leads_path.exists():
        return []
    tokens = tokenize_topic(topic)
    hits: List[str] = []
    for line in leads_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip() or line.startswith("|") and "---" in line:
            continue
        if tokens and score_text(line, tokens) == 0:
            continue
        hits.append(line.strip())
        if len(hits) >= max_lines:
            break
    return hits


def build_summary(topic: str, reports: List[dict], leads: List[str]) -> str:
    lines = [f"=== Brief Intel: {topic} ===", ""]
    if reports:
        lines.append("Desde reportes Intel:")
        for rep in reports:
            lines.append(f"- {rep['file']}:")
            for b in rep["bullets"][:5]:
                lines.append(f"  • {b.lstrip('-*• ')}")
    else:
        lines.append("Sin reportes Intel recientes para este tema (pide a Intel investigar o usa web_search).")
    if leads:
        lines.append("")
        lines.append("Señales en leads:")
        for row in leads[:6]:
            lines.append(f"  • {row}")
    lines.append("")
    lines.append("Siguiente paso: web_search si necesitas tendencias de esta semana.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Brief desde workspace Intel.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--reports-dir", default=DEFAULT_INTEL_REPORTS)
    parser.add_argument("--leads", default=DEFAULT_INTEL_LEADS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    reports_dir = resolve_data_path(args.reports_dir)
    leads_path = resolve_data_path(args.leads)
    reports = load_report_snippets(reports_dir, args.topic)
    leads = load_leads_snippet(leads_path, args.topic)
    payload = {
        "topic": args.topic,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_files": [r["file"] for r in reports],
        "leads_hits": leads,
        "summary": build_summary(args.topic, reports, leads),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["summary"])


if __name__ == "__main__":
    main()
