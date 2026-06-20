#!/usr/bin/env python3
"""Experiencia laboral canónica para portales (Laborum, ChileTrabajos, etc.)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jobs_common import ROOT, load_config

PROFILE_PATH = ROOT / "config/jobs/profile_experience.json"


def profile_path(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_config()
    raw = cfg.get("profile_experience_path") or "config/jobs/profile_experience.json"
    path = Path(raw)
    return path if path.is_absolute() else ROOT / raw


def load_experiences(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    path = profile_path(cfg)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = list(payload.get("experiences") or [])
    items.sort(key=lambda row: str(row.get("start") or ""), reverse=True)
    return items


def best_cv_path(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_config()
    profile = json.loads(profile_path(cfg).read_text(encoding="utf-8")) if profile_path(cfg).exists() else {}
    raw = profile.get("source_cv") or cfg.get("default_cv") or "content/CV/CV_MauricioCastro-IaC-022026.pdf"
    path = Path(raw)
    return path if path.is_absolute() else ROOT / raw
