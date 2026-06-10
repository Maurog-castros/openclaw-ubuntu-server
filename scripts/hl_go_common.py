"""Rutas y utilidades compartidas del agente HL-Go."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

OPENCLAW_ROOT = Path("/home/node/openclaw-mauro")
if not OPENCLAW_ROOT.exists():
    OPENCLAW_ROOT = Path(__file__).resolve().parent.parent

HL_MIKO_REPO = os.getenv("HL_MIKO_REPO", "")
HL_GO_APP = os.getenv("HL_GO_APP", "")

REPO_URL = "https://github.com/Maurog-castros/hl_miko.git"
# origin/HEAD → dev.h-l.cl (rama activa del proyecto HL-Go)
DEFAULT_BRANCH = "dev.h-l.cl"
OPENCLAW_WORK_BRANCH = "openclaw/mantenedores-tablas-ui-20260528"
GIT_CREDENTIALS = OPENCLAW_ROOT / "secrets/github_hl_miko_credentials"
ENV_SOURCE = OPENCLAW_ROOT / "secrets/hl_go.env"
APP_URL_DEFAULT = "http://localhost:8001"


def _resolve_repo_root() -> Path:
    if HL_MIKO_REPO:
        return Path(HL_MIKO_REPO).resolve()
    for candidate in (
        Path("/home/node/.openclaw/workspace/projects/hl_miko"),
        OPENCLAW_ROOT / "projects/hl_miko",
        Path("/home/mauro/Dev/hl_miko"),
    ):
        if candidate.exists():
            return candidate.resolve()
    return Path("/home/node/.openclaw/workspace/projects/hl_miko").resolve()


def repo_root() -> Path:
    return _resolve_repo_root()


def app_root() -> Path:
    if HL_GO_APP:
        return Path(HL_GO_APP).resolve()
    return repo_root() / "HL-Go"


def env_file() -> Path:
    return app_root() / ".env"


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    target = path or env_file()
    out: dict[str, str] = {}
    if not target.exists():
        return out
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        out[key] = value
    return out


def app_url(cfg: dict[str, str] | None = None) -> str:
    cfg = cfg or load_dotenv()
    return (cfg.get("APP_URL") or APP_URL_DEFAULT).rstrip("/")


def current_branch(*, cwd: Path | None = None) -> str:
    proc = run_git(["branch", "--show-current"], cwd=cwd)
    return (proc.stdout or "").strip()


def normalize_branch_name(name: str) -> str:
    """Canonical git branch; never treat «principal» as a literal branch name."""
    n = (name or "").strip().strip("`\"'")
    low = n.lower()
    if low in {"principal", "prod", "produccion", "producción", "la", "el", "a"}:
        return DEFAULT_BRANCH
    if low in {"main", "master"}:
        return "main"
    if low == DEFAULT_BRANCH.lower() or re.fullmatch(r"dev\.h-?l\.?cl", low):
        return DEFAULT_BRANCH
    if "openclaw" in low or "mantenedores" in low:
        return OPENCLAW_WORK_BRANCH
    return n


def resolve_branch_from_text(text: str) -> str | None:
    """Map natural language to a git branch name (hl_miko)."""
    raw = (text or "").strip()
    if not raw:
        return None
    if re.search(r"\bopenclaw\b|\bmantenedores\b", raw, re.I):
        return OPENCLAW_WORK_BRANCH
    if re.search(r"\bmain\b", raw, re.I) and not re.search(r"rama\s+principal", raw, re.I):
        return "main"
    # «rama principal» = origin/HEAD = dev.h-l.cl (nunca crear rama local «principal»)
    if re.search(
        r"rama\s+principal|principal\s+remot[ao]?|\bprincipal\b|dev\.h-?l\.?cl\b",
        raw,
        re.I,
    ):
        return DEFAULT_BRANCH
    m = re.search(
        r"(?:\brama\b|\bcheckout\b|\bbranch\b)\s+"
        r"(?:a\s+(?:la\s+|el\s+)?|en\s+|hacia\s+)?(?:rama\s+)?"
        r"[`\"']?([a-zA-Z0-9._/-]+)[`\"']?",
        raw,
        re.I,
    )
    if m:
        return normalize_branch_name(m.group(1))
    return None


def _remote_ref_exists(root: Path, branch: str) -> bool:
    proc = run_git(["show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}"], cwd=root)
    return proc.returncode == 0


def _delete_local_branch_if_no_remote(root: Path, branch: str) -> None:
    if branch == DEFAULT_BRANCH:
        return
    listed = run_git(["branch", "--list", branch], cwd=root)
    if not (listed.stdout or "").strip():
        return
    if _remote_ref_exists(root, branch):
        return
    run_git(["branch", "-D", branch], cwd=root)


def checkout_branch(branch: str, *, cwd: Path | None = None) -> dict[str, Any]:
    root = cwd or repo_root()
    target = normalize_branch_name(resolve_branch_from_text(branch) or branch)

    fetch = run_git(["fetch", "origin", "--prune"], cwd=root)

    remote_ref = f"origin/{target}"
    if _remote_ref_exists(root, target):
        checkout = run_git(["checkout", "-B", target, remote_ref], cwd=root)
    else:
        listed = run_git(["branch", "--list", target], cwd=root)
        if not (listed.stdout or "").strip():
            return {
                "ok": False,
                "branch": target,
                "stderr": (
                    f"La rama `{target}` no existe en origin. "
                    f"Rama principal remota: `{DEFAULT_BRANCH}` (origin/HEAD)."
                ),
                "fetch_ok": fetch.returncode == 0,
            }
        checkout = run_git(["checkout", target], cwd=root)

    if checkout.returncode != 0:
        return {
            "ok": False,
            "branch": target,
            "stderr": (checkout.stderr or checkout.stdout or "").strip()[-500:],
            "fetch_ok": fetch.returncode == 0,
        }

    pull = run_git(["pull", "--ff-only"], cwd=root)
    tracked = _remote_ref_exists(root, target)
    # Tras cambiar a la rama remota real, eliminar «principal» local huérfana si quedó
    if target == DEFAULT_BRANCH:
        _delete_local_branch_if_no_remote(root, "principal")
    return {
        "ok": True,
        "branch": current_branch(cwd=root),
        "requested": target,
        "tracked_remote": tracked,
        "remote_ref": remote_ref if tracked else "",
        "pull_ok": pull.returncode == 0,
        "pull_stdout": (pull.stdout or "").strip()[-300:],
        "pull_stderr": (pull.stderr or "").strip()[-300:],
        "fetch_ok": fetch.returncode == 0,
    }


def run_git(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = ["git", *args]
    env = os.environ.copy()
    if GIT_CREDENTIALS.exists():
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "credential.helper"
        env["GIT_CONFIG_VALUE_0"] = f"store --file={GIT_CREDENTIALS}"
    return subprocess.run(
        cmd,
        cwd=str(cwd or repo_root()),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def _ensure_symlink(path: Path, target: Path) -> None:
    if not target.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        try:
            if path.resolve() == target.resolve():
                return
        except OSError:
            pass
        path.unlink()
    elif path.exists():
        return
    path.symlink_to(target)


def ensure_repo_symlink() -> Path:
    target = repo_root()
    if not target.exists():
        return target

    repos_link = Path("/home/node/repos/hl_miko")
    _ensure_symlink(repos_link, target)

    link = OPENCLAW_ROOT / "projects/hl_miko"
    projects_parent = link.parent
    if projects_parent.exists() and os.access(projects_parent, os.W_OK):
        _ensure_symlink(link, target)
    return target


def port_open(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def parse_port_from_url(url: str) -> int:
    m = re.search(r":(\d+)(?:/|$)", url)
    return int(m.group(1)) if m else 8001
