#!/usr/bin/env python3
"""Clona hl_miko, escribe .env local y deja symlinks en el workspace."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from hl_go_common import (
    ENV_SOURCE,
    OPENCLAW_ROOT,
    REPO_URL,
    app_root,
    ensure_repo_symlink,
    env_file,
    repo_root,
    run_git,
)

EXAMPLE_ENV = OPENCLAW_ROOT / "config/hl-go/hl_go.env.example"


def clone_or_pull(target: Path) -> dict[str, str]:
    if (target / ".git").is_dir():
        proc = run_git(["pull", "--ff-only"], cwd=target)
        return {
            "action": "pull",
            "ok": proc.returncode == 0,
            "stdout": proc.stdout.strip()[-500:],
            "stderr": proc.stderr.strip()[-500:],
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    proc = run_git(["clone", REPO_URL, str(target)])
    return {
        "action": "clone",
        "ok": proc.returncode == 0,
        "stdout": proc.stdout.strip()[-500:],
        "stderr": proc.stderr.strip()[-500:],
    }


def write_env(*, force: bool) -> dict[str, str]:
    app = app_root()
    app.mkdir(parents=True, exist_ok=True)
    dest = env_file()
    source = ENV_SOURCE
    if not source.exists():
        try:
            source.parent.mkdir(parents=True, exist_ok=True)
            if EXAMPLE_ENV.exists():
                shutil.copy2(EXAMPLE_ENV, source)
            else:
                return {
                    "action": "error",
                    "path": str(source),
                    "ok": False,
                    "hint": f"Copia {EXAMPLE_ENV} a {source}",
                }
        except OSError:
            if dest.exists():
                return {"action": "skip", "path": str(dest), "ok": True}
            return {"action": "error", "path": str(source), "ok": False}
    if dest.exists() and not force:
        return {"action": "skip", "path": str(dest), "ok": True}
    shutil.copy2(source, dest)
    return {"action": "write", "path": str(dest), "ok": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup HL-Go repo + .env")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--force-env", action="store_true", help="Sobrescribe HL-Go/.env")
    parser.add_argument("--skip-clone", action="store_true", help="No clone/pull; solo symlinks + env")
    parser.add_argument("--pull-only", action="store_true", help="Solo git pull/clone + symlink; sin tocar .env")
    args = parser.parse_args()

    target = repo_root()
    result: dict[str, object] = {"repo": str(target), "app": str(app_root())}

    if args.pull_only:
        result["git"] = clone_or_pull(target)
        result["symlink"] = str(ensure_repo_symlink())
        result["ok"] = bool(result["git"].get("ok"))
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 1

    if not args.skip_clone and not (target / ".git").is_dir():
        result["git"] = clone_or_pull(target)
        if not result["git"]["ok"]:
            print(json.dumps({"ok": False, **result}, ensure_ascii=False), file=sys.stderr)
            return 1
    elif not args.skip_clone:
        result["git"] = clone_or_pull(target)

    result["symlink"] = str(ensure_repo_symlink())
    result["env"] = write_env(force=args.force_env)

    php = shutil.which("php")
    result["php"] = php or ""
    if php and (app_root() / "start.sh").exists():
        check = subprocess.run([php, "-v"], text=True, capture_output=True, check=False)
        result["php_version"] = (check.stdout or check.stderr).splitlines()[0] if check.returncode == 0 else ""

    result["ok"] = True
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"HL-Go listo: {app_root()}")
        print(f".env: {env_file()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
