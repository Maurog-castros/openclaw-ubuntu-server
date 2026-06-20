#!/usr/bin/env python3
"""Perfiles Jobs multi-persona: registry, rutas y utilidades."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from runtime_paths import repo_root, resolve_repo_path

ROOT = repo_root()
REGISTRY_PATH = ROOT / "config/jobs/profiles.json"
PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
PROFILE_TEXT_RE = re.compile(r"(?:^|\s)(?:@|perfil\s+)([a-z][a-z0-9_-]{1,31})\b", re.I)


@dataclass(frozen=True)
class JobsProfile:
    profile_id: str
    label: str
    config_path: Path
    workspace: Path
    spreadsheet_id: str
    cv_dir: Path
    secrets_dir: Path

    def env(self) -> dict[str, str]:
        return {
            "OPENCLAW_JOBS_PROFILE": self.profile_id,
            "OPENCLAW_JOBS_DATA": str(self.workspace),
            "OPENCLAW_JOBS_CONFIG": str(self.config_path),
        }


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"default": "mauro", "profiles": {}}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(data: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _as_path(raw: str) -> Path:
    return resolve_repo_path(raw)


def _profile_from_entry(profile_id: str, entry: dict[str, Any]) -> JobsProfile:
    return JobsProfile(
        profile_id=profile_id,
        label=str(entry.get("label") or profile_id),
        config_path=_as_path(str(entry["config_path"])),
        workspace=_as_path(str(entry["workspace"])),
        spreadsheet_id=str(entry.get("spreadsheet_id") or ""),
        cv_dir=_as_path(str(entry.get("cv_dir") or "runtime/jobs/cv-library")),
        secrets_dir=_as_path(str(entry.get("secrets_dir") or f"runtime/secrets/jobs/{profile_id}")),
    )


def list_profiles() -> list[JobsProfile]:
    registry = load_registry()
    profiles = registry.get("profiles") or {}
    return [_profile_from_entry(pid, entry) for pid, entry in sorted(profiles.items())]


def get_profile(profile_id: str | None = None) -> JobsProfile:
    registry = load_registry()
    profiles = registry.get("profiles") or {}
    pid = (profile_id or os.environ.get("OPENCLAW_JOBS_PROFILE") or registry.get("default") or "").strip().lower()
    if not pid:
        raise KeyError("No hay perfil Jobs activo.")
    if pid not in profiles:
        known = ", ".join(sorted(profiles)) or "(ninguno)"
        raise KeyError(f"Perfil Jobs '{pid}' no existe. Disponibles: {known}")
    return _profile_from_entry(pid, profiles[pid])


def get_default_profile() -> JobsProfile:
    registry = load_registry()
    return get_profile(str(registry.get("default") or "mauro"))


def resolve_runtime_paths() -> tuple[Path, Path, str]:
    if os.environ.get("OPENCLAW_JOBS_DATA"):
        workspace = Path(os.environ["OPENCLAW_JOBS_DATA"]).expanduser()
        if os.environ.get("OPENCLAW_JOBS_CONFIG"):
            config_path = Path(os.environ["OPENCLAW_JOBS_CONFIG"]).expanduser()
        else:
            config_path = ROOT / "config/jobs/config.json"
        profile_id = os.environ.get("OPENCLAW_JOBS_PROFILE", "")
        return workspace, config_path, profile_id

    profile = get_profile()
    return profile.workspace, profile.config_path, profile.profile_id


def parse_profile_from_text(text: str) -> tuple[str, str | None]:
    match = PROFILE_TEXT_RE.search(text or "")
    if not match:
        return text, None
    profile_id = match.group(1).lower()
    cleaned = PROFILE_TEXT_RE.sub(" ", text).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned, profile_id


def validate_profile_id(profile_id: str) -> None:
    if not PROFILE_ID_RE.fullmatch(profile_id):
        raise ValueError(
            "profile_id invalido. Usa minusculas, numeros, guion o underscore (2-32 chars, empieza con letra)."
        )


def workspace_subdirs(workspace: Path) -> list[Path]:
    names = ("vacancies", "laborum", "applications", "reports", "cv_rankings")
    return [workspace / name for name in names]
