#!/usr/bin/env python3
"""Crea carpeta, config y registry para un perfil Jobs nuevo."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jobs_profile import (
    REGISTRY_PATH,
    ROOT,
    JobsProfile,
    get_profile,
    load_registry,
    save_registry,
    validate_profile_id,
    workspace_subdirs,
)
from runtime_paths import cv_library_dir, secrets_dir as runtime_secrets_dir

TEMPLATE_CONFIG = ROOT / "config/jobs/profiles/_template.json"
TEMPLATE_EXPERIENCE = {
    "owner": "",
    "updated_at": "",
    "source_cv": "",
    "experiences": [],
}


def render_template(text: str, profile_id: str, label: str) -> str:
    return text.replace("PERFIL_ID", profile_id).replace("Nombre Apellido", label)


def init_profile(
    profile_id: str,
    label: str,
    *,
    spreadsheet_id: str = "",
    target_roles: list[str] | None = None,
    core_skills: list[str] | None = None,
    copy_from: str = "",
) -> JobsProfile:
    validate_profile_id(profile_id)
    registry = load_registry()
    profiles = registry.setdefault("profiles", {})
    if profile_id in profiles:
        raise FileExistsError(f"El perfil '{profile_id}' ya existe en {REGISTRY_PATH}")

    if copy_from:
        source = get_profile(copy_from)
        workspace = ROOT / f"data/workspace/jobs/{profile_id}"
        config_path = ROOT / f"config/jobs/profiles/{profile_id}.json"
        experience_path = ROOT / f"config/jobs/profiles/{profile_id}_experience.json"
        cv_dir = cv_library_dir() / profile_id
        secrets_path = runtime_secrets_dir() / "jobs" / profile_id
        cfg = json.loads(source.config_path.read_text(encoding="utf-8"))
        cfg["owner"] = label
        cfg["cv_dir"] = f"runtime/jobs/cv-library/{profile_id}"
        cfg["applications_csv"] = f"data/workspace/jobs/{profile_id}/applications.csv"
        cfg["profile_experience_path"] = f"config/jobs/profiles/{profile_id}_experience.json"
        cfg["linkedin_storage_state"] = f"runtime/secrets/jobs/{profile_id}/linkedin_storage_state.json"
        cfg["chiletrabajos"]["storage_state"] = f"runtime/secrets/jobs/{profile_id}/chiletrabajos_storage_state.json"
        cfg["computrabajo"]["storage_state"] = f"runtime/secrets/jobs/{profile_id}/computrabajo_storage_state.json"
        cfg["job_portals"]["laborum"]["storage_state"] = f"runtime/secrets/jobs/{profile_id}/laborum_storage_state.json"
    else:
        workspace = ROOT / f"data/workspace/jobs/{profile_id}"
        config_path = ROOT / f"config/jobs/profiles/{profile_id}.json"
        experience_path = ROOT / f"config/jobs/profiles/{profile_id}_experience.json"
        cv_dir = cv_library_dir() / profile_id
        secrets_path = runtime_secrets_dir() / "jobs" / profile_id
        raw = TEMPLATE_CONFIG.read_text(encoding="utf-8")
        cfg = json.loads(render_template(raw, profile_id, label))

    if target_roles:
        cfg["target_roles"] = target_roles
    if core_skills:
        cfg["core_skills"] = core_skills

    for path in workspace_subdirs(workspace):
        path.mkdir(parents=True, exist_ok=True)
    cv_dir.mkdir(parents=True, exist_ok=True)
    secrets_path.mkdir(parents=True, exist_ok=True)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    experience = dict(TEMPLATE_EXPERIENCE)
    experience["owner"] = label
    experience_path.write_text(json.dumps(experience, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    entry = {
        "label": label,
        "config_path": str(config_path.relative_to(ROOT)),
        "workspace": str(workspace.relative_to(ROOT)),
        "spreadsheet_id": spreadsheet_id,
        "cv_dir": str(cv_dir.relative_to(ROOT)),
        "secrets_dir": str(secrets_path.relative_to(ROOT)),
    }
    profiles[profile_id] = entry
    save_registry(registry)
    return get_profile(profile_id)


def setup_sheet(profile: JobsProfile, *, apply: bool) -> dict[str, Any]:
    if not profile.spreadsheet_id:
        return {"status": "skipped", "reason": "sin spreadsheet_id"}
    from jobs_google_sheet_setup import setup

    if not apply:
        return {
            "status": "dry_run",
            "spreadsheet_id": profile.spreadsheet_id,
            "profile": profile.profile_id,
        }
    return setup(profile.spreadsheet_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Crear perfil nuevo")
    create.add_argument("profile_id")
    create.add_argument("label")
    create.add_argument("--spreadsheet-id", default="")
    create.add_argument("--copy-from", default="", help="Clonar config base de otro perfil")
    create.add_argument("--role", action="append", default=[], dest="roles")
    create.add_argument("--skill", action="append", default=[], dest="skills")
    create.add_argument("--setup-sheet", action="store_true")
    create.add_argument("--apply", action="store_true")

    sub.add_parser("list", help="Listar perfiles")

    show = sub.add_parser("show", help="Mostrar un perfil")
    show.add_argument("profile_id")

    args = parser.parse_args()

    if args.command == "list":
        payload = {
            "default": load_registry().get("default"),
            "profiles": [
                {
                    "id": p.profile_id,
                    "label": p.label,
                    "workspace": str(p.workspace),
                    "config_path": str(p.config_path),
                    "spreadsheet_id": p.spreadsheet_id,
                    "cv_dir": str(p.cv_dir),
                }
                for p in __import__("jobs_profile").list_profiles()
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "show":
        profile = get_profile(args.profile_id)
        print(json.dumps({
            "profile_id": profile.profile_id,
            "label": profile.label,
            "workspace": str(profile.workspace),
            "config_path": str(profile.config_path),
            "spreadsheet_id": profile.spreadsheet_id,
            "cv_dir": str(profile.cv_dir),
            "secrets_dir": str(profile.secrets_dir),
        }, ensure_ascii=False, indent=2))
        return

    profile = init_profile(
        args.profile_id,
        args.label,
        spreadsheet_id=args.spreadsheet_id,
        target_roles=args.roles or None,
        core_skills=args.skills or None,
        copy_from=args.copy_from,
    )
    result: dict[str, Any] = {
        "status": "ok",
        "profile_id": profile.profile_id,
        "label": profile.label,
        "workspace": str(profile.workspace),
        "config_path": str(profile.config_path),
        "cv_dir": str(profile.cv_dir),
        "secrets_dir": str(profile.secrets_dir),
        "next_steps": [
            f"Pon CVs PDF en {profile.cv_dir}",
            f"Login LinkedIn: OPENCLAW_JOBS_PROFILE={profile.profile_id} .venv-linkedin-intel/bin/python scripts/jobs_linkedin_login.py login --headed",
            f"Indexar: /jobs @{profile.profile_id} indexar cv",
            f"Buscar: /jobs @{profile.profile_id} buscar linkedin",
        ],
    }
    if args.setup_sheet:
        result["sheet"] = setup_sheet(profile, apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
