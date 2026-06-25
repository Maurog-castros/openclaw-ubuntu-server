"""Utilidades compartidas agente Jobs (postulaciones)."""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from runtime_paths import repo_root, resolve_repo_path

ROOT = repo_root()


def _bootstrap_paths() -> tuple[Path, Path, str]:
    from jobs_profile import resolve_runtime_paths

    return resolve_runtime_paths()


JOBS_WS, CONFIG_PATH, ACTIVE_PROFILE_ID = _bootstrap_paths()
CV_INDEX = JOBS_WS / "cv_index.json"
APPLICATIONS = JOBS_WS / "applications"
APPLICATIONS_JSONL = JOBS_WS / "applications.jsonl"


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def cv_dir(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_config()
    raw = cfg.get("cv_dir") or "runtime/jobs/cv-library"
    return resolve_repo_path(raw)


def list_cv_files(cfg: dict[str, Any] | None = None) -> list[Path]:
    cfg = cfg or load_config()
    base = cv_dir(cfg)
    if not base.exists():
        return []
    globs = cfg.get("cv_include_globs") or ["Mauricio*.pdf", "CV_Mauricio*.pdf"]
    excludes = [x.lower() for x in (cfg.get("cv_exclude_patterns") or [])]
    found: list[Path] = []
    for pattern in globs:
        found.extend(base.glob(pattern))
    out: list[Path] = []
    for path in sorted(set(found)):
        name = path.name.lower()
        if any(ex in name for ex in excludes):
            continue
        if path.suffix.lower() == ".pdf":
            out.append(path)
    return out


def extract_pdf_text(path: Path, max_pages: int = 6) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Falta pypdf en el venv finanzas.") from exc
    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    text = re.sub(r"\s+", " ", " ".join(parts)).strip()
    return text


def infer_cv_tags(name: str, text: str) -> list[str]:
    blob = f"{name} {text}".lower()
    tags: list[str] = []
    mapping = {
        "devops": ["devops", "devsecops"],
        "sre": ["sre", "site reliability", "reliability engineer"],
        "kubernetes": ["kubernetes", "k8s", "eks", "argocd", "gitops"],
        "cloud": ["cloud engineer", "cloud architect", "cloudops", "multi-cloud"],
        "iac": ["terraform", "cloudformation", "infrastructure as code", "iac"],
        "mlops": ["mlops", "kubeflow", "model"],
        "ai": ["ai engineer", "ai developer", "llm", "rag", "bedrock", "openai"],
        "data": ["data engineer", "etl", "big data", "step functions"],
        "techlead": ["tech lead", "technical lead", "full stack", "node.js", "react"],
        "premium": ["premium", "devsecops"],
    }
    for tag, terms in mapping.items():
        if any(t in blob for t in terms):
            tags.append(tag)
    return tags or ["general"]


def is_job_post(text: str, cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or load_config()
    low = f" {text.lower()} "
    hits = sum(1 for t in cfg.get("job_post_terms", []) if t in low)
    return hits >= 2 or (
        hits >= 1 and any(r in low for r in ["devops", "sre", "cloud", "kubernetes", "mlops", "platform"])
    )


def score_vacancy(text: str, cfg: dict[str, Any] | None = None) -> int:
    cfg = cfg or load_config()
    low = f" {text.lower()} "
    score = 0
    for skill in cfg.get("core_skills", []):
        if skill in low:
            score += 3
    for role in cfg.get("target_roles", []):
        if role.lower() in low:
            score += 5
    for term in cfg.get("demote_terms", []):
        if term in low:
            score -= 8
    if "chile" in low or "santiago" in low or "remoto chile" in low or "latam" in low:
        score += 6
    if "remote" in low or "remoto" in low or "híbrido" in low or "hibrido" in low:
        score += 2
    return score


def pick_best_cv(vacancy_text: str, cv_index: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not cv_index:
        return None
    low = vacancy_text.lower()
    best: tuple[int, dict[str, Any]] | None = None
    for cv in cv_index:
        score = 0
        for tag in cv.get("tags") or []:
            if tag == "devops" and any(x in low for x in ("devops", "devsecops", "ci/cd")):
                score += 8
            if tag == "sre" and "sre" in low:
                score += 10
            if tag == "kubernetes" and any(x in low for x in ("kubernetes", "k8s", "eks", "argocd")):
                score += 8
            if tag == "mlops" and "mlops" in low:
                score += 10
            if tag == "ai" and any(x in low for x in ("ai", "llm", "machine learning", "ia")):
                score += 8
            if tag == "data" and "data engineer" in low:
                score += 10
            if tag == "techlead" and any(x in low for x in ("tech lead", "technical lead", "full stack")):
                score += 8
            if tag == "cloud" and "cloud" in low:
                score += 5
            if tag == "iac" and any(x in low for x in ("terraform", "iac", "cloudformation")):
                score += 7
        for kw in re.findall(r"[a-z0-9+#./]{3,}", cv.get("filename", "").lower()):
            if kw in low:
                score += 2
        if best is None or score > best[0]:
            best = (score, cv)
    return best[1] if best else cv_index[0]


def load_linkedin_job_signals(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = cfg or load_config()
    pattern = cfg.get("linkedin_signals_glob") or "data/workspace/marketing/intel/data/linkedin_signals_*.json"
    files = sorted(ROOT.glob(pattern), reverse=True)
    if not files:
        return []
    try:
        payload = json.loads(files[0].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    signals = list(payload.get("signals") or [])
    jobs = []
    for sig in signals:
        text = sig.get("text") or ""
        if is_job_post(text, cfg):
            jobs.append(sig)
    return jobs


def load_last_matches() -> list[dict[str, Any]]:
    path = JOBS_WS / "last_matches.json"
    if not path.exists():
        return []
    try:
        return list(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return []


def resolve_vacancy(text: str, index: int | None) -> dict[str, Any]:
    matches = load_last_matches()
    if index is not None and 1 <= index <= len(matches):
        return matches[index - 1]
    if text and len(text) > 50:
        return {"source": "manual", "text": text, "url": "", "match_score": 0}
    raise ValueError("Indica numero de vacante (ej. postular 2) o pega URL LinkedIn Jobs.")


def parse_vacancy_index(text: str) -> int | None:
    m = re.search(r"(?:aplicar|postular|vacante)\s*#?(\d{1,2})\b", text, re.I)
    return int(m.group(1)) if m else None


def vacancy_title(text: str) -> str:
    for sep in (" • ", " — ", " | ", "\n"):
        if sep in text:
            return text.split(sep)[0].strip()[:120]
    return text[:120].strip()


DOCKER_NODE_UID = int(os.environ.get("OPENCLAW_NODE_UID", "1000"))
DOCKER_NODE_GID = int(os.environ.get("OPENCLAW_NODE_GID", "1000"))


def ensure_gateway_writable(path: Path) -> None:
    """Gateway Docker escribe como node (uid 1000). Evita Permission denied en job.json."""
    try:
        if path.is_dir():
            path.chmod(0o2775)
        else:
            path.chmod(0o664)
        os.chown(path, DOCKER_NODE_UID, DOCKER_NODE_GID)
    except OSError:
        pass
