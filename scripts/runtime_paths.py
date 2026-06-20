"""Canonical runtime paths with legacy alias resolution."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent

LEGACY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("content/CV", "runtime/jobs/cv-library"),
    ("data/CV", "runtime/jobs/cv-library"),
    ("data/secrets", "runtime/secrets"),
    ("secrets", "runtime/secrets"),
    ("logs", "runtime/logs"),
)


def repo_root() -> Path:
    override = os.environ.get("OPENCLAW_REPO_ROOT", "").strip()
    if override:
        return Path(override).expanduser()
    return ROOT


def cv_library_dir() -> Path:
    return repo_root() / "runtime/jobs/cv-library"


def secrets_dir() -> Path:
    return repo_root() / "runtime/secrets"


def logs_dir() -> Path:
    return repo_root() / "runtime/logs"


def resolve_repo_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    text = path.as_posix()
    for legacy, canonical in LEGACY_PREFIXES:
        if text == legacy or text.startswith(f"{legacy}/"):
            suffix = text[len(legacy) :].lstrip("/")
            target = repo_root() / canonical
            return target / suffix if suffix else target
    return repo_root() / path


def secret_file(relative: str) -> Path:
    return resolve_repo_path(relative)
