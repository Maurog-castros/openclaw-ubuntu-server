#!/usr/bin/env python3
"""Delegate /hl y /hlgo — setup, validar, contexto HL-Go."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent

PY = str(ROOT / ".venv-linkedin-intel/bin/python")
if not Path(PY).exists():
    PY = str(ROOT / ".venv-finanzas/bin/python")
if not Path(PY).exists():
    PY = "python3"

SCR = str(ROOT / "scripts")
sys.path.insert(0, SCR)
from hl_go_common import checkout_branch, current_branch, repo_root, resolve_branch_from_text

HL_PREFIX_RE = re.compile(r"^\s*/(?:hl|hlgo|hl-go)\b", re.I)
PULL_RE = re.compile(r"\b(pull|actualizar?\s+(?:el\s+)?repo|clonar?|clone)\b", re.I)
BRANCH_RE = re.compile(
    r"\b(cambiar?\w*\s+(?:de\s+)?rama|cambiate?\s+(?:de\s+)?rama|checkout|"
    r"switch\s+branch|pasarte?\s+a\s+(?:la\s+)?rama|rama\s+principal)\b",
    re.I,
)
SETUP_RE = re.compile(r"\b(setup|init)\b", re.I)
VALIDATE_RE = re.compile(r"\b(validar?|qa|playwright|smoke|probar|test)\b", re.I)
STATUS_RE = re.compile(r"\b(status|estado|info|contexto)\b", re.I)
SUMMARY_RE = re.compile(r"\b(resumen|ultimo|último|ultimos|últimos|que\s+hay|novedades)\b", re.I)


def run_json(cmd: list[str], timeout: int = 300) -> tuple[int, dict[str, Any], str, str]:
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout, check=False)
    payload: dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"whatsapp_reply": proc.stdout.strip()}
    return proc.returncode, payload, proc.stdout, proc.stderr


def run_hl_agent(message: str, session_key: str) -> tuple[int, str, str, str]:
    cmd = [
        "openclaw", "agent", "--local", "--agent", "hlgo",
        "--session-key", session_key, "--message", message, "--json",
    ]
    code, payload, stdout, stderr = run_json(cmd, timeout=300)
    reply = ""
    for item in payload.get("payloads") or []:
        if isinstance(item, dict) and item.get("text"):
            reply = str(item["text"]).strip()
            break
    if not reply:
        reply = str(payload.get("whatsapp_reply") or "").strip()
    return code, reply, stdout, stderr


def run_git(repo: Path, *args: str, timeout: int = 30) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return (proc.stdout or proc.stderr or "").strip()


def summarize_latest() -> dict[str, Any]:
    repo = repo_root()
    branch_name = current_branch() or "?"
    status = run_git(repo, "status", "--short")
    commits = run_git(
        repo,
        "log",
        "-5",
        "--date=format-local:%d-%m-%Y %H:%M",
        "--pretty=format:%h%x09%ad%x09%d%x09%s",
    )
    changed = [line for line in status.splitlines() if line.strip()]
    lines = [
        "HL-Go — último contexto",
        f"Rama: {branch_name}",
        "Commits:",
    ]
    for commit in commits.splitlines()[:5]:
        parts = commit.split("\t", 3)
        if len(parts) != 4:
            lines.append(f"• {commit[:110]}")
            continue
        commit_hash, committed_at, refs, subject = parts
        ref_text = f" {refs.strip()}" if refs.strip() else ""
        lines.append(f"• {committed_at} {commit_hash}{ref_text} {subject}"[:110])
    if changed:
        lines.append(f"Cambios sin commit: {len(changed)} archivo(s).")
        lines.extend(f"• {line[:100]}" for line in changed[:5])
    else:
        lines.append("Working tree limpio.")
    return {
        "status": "ok",
        "agent": "hlgo",
        "repo": str(repo),
        "branch": branch_name,
        "dirty_count": len(changed),
        "whatsapp_reply": "\n".join(lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Delegate HL-Go agent")
    parser.add_argument("--text", required=True)
    parser.add_argument("--session-key", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    message = HL_PREFIX_RE.sub("", args.text or "").strip()
    session_key = args.session_key or "hlgo:whatsapp"

    if BRANCH_RE.search(message) or resolve_branch_from_text(message):
        target = resolve_branch_from_text(message)
        if not target:
            out = {
                "status": "error",
                "agent": "hlgo",
                "whatsapp_reply": (
                    "Indica la rama. Ejemplos:\n"
                    "• /hlgo rama principal → dev.h-l.cl\n"
                    "• /hlgo checkout openclaw/mantenedores-tablas-ui-20260528\n"
                    "• /hlgo rama main"
                ),
            }
            print(json.dumps(out, ensure_ascii=False))
            return
        result = checkout_branch(target)
        repo = str(repo_root())
        if not result.get("ok"):
            out = {
                "status": "error",
                "agent": "hlgo",
                "whatsapp_reply": (
                    f"HL-Go checkout fallo\nRepo: {repo}\n"
                    f"Rama pedida: {target}\n{(result.get('stderr') or '')[-350:]}"
                ),
            }
        else:
            pull_note = (result.get("pull_stdout") or "").splitlines()
            summary = pull_note[-1] if pull_note else "sin cambios"
            if not result.get("pull_ok"):
                summary = f"checkout OK; pull: {(result.get('pull_stderr') or 'fallo')[-120:]}"
            remote = result.get("remote_ref") or ""
            track = " (tracking origin)" if result.get("tracked_remote") else ""
            remote_line = f"Remoto: {remote}\n" if remote else ""
            out = {
                "status": "ok",
                "agent": "hlgo",
                "ok": True,
                "repo": repo,
                "branch": result.get("branch"),
                "whatsapp_reply": (
                    f"HL-Go checkout OK\nRepo: {repo}\n"
                    f"Rama: {result.get('branch')}{track}\n"
                    f"{remote_line}{summary}"
                ),
            }
        print(json.dumps(out, ensure_ascii=False))
        return

    if PULL_RE.search(message):
        code, payload, _, stderr = run_json(
            [PY, f"{SCR}/hl_go_setup.py", "--json", "--pull-only"],
            timeout=180,
        )
        git = payload.get("git") if isinstance(payload.get("git"), dict) else {}
        if code != 0 or not payload.get("ok", True):
            payload = {
                "ok": False,
                "whatsapp_reply": f"HL-Go git fallo: {(git.get('stderr') or stderr)[-400:]}",
            }
        else:
            repo = str(payload.get("repo") or "")
            branch_name = current_branch() or "?"
            action = git.get("action") or "pull"
            git_out = (git.get("stdout") or "Already up to date.").strip()
            summary = git_out.splitlines()[-1] if git_out else "sin cambios"
            payload["whatsapp_reply"] = (
                f"HL-Go {action} OK\n"
                f"Repo: {repo}\n"
                f"Rama: {branch_name}\n"
                f"{summary}"
            )
            payload["status"] = "ok"
        payload.setdefault("agent", "hlgo")
        print(json.dumps(payload, ensure_ascii=False))
        return

    if not message or SETUP_RE.search(message):
        code, payload, _, stderr = run_json(
            [PY, f"{SCR}/hl_go_setup.py", "--json", "--skip-clone"],
            timeout=120,
        )
        if code != 0:
            payload = {"ok": False, "whatsapp_reply": f"HL-Go setup fallo: {stderr[-400:]}"}
        else:
            app = payload.get("app", "HL-Go")
            payload["whatsapp_reply"] = f"HL-Go listo.\nRepo: {payload.get('repo')}\nApp: {app}\n.env: OK"
        payload.setdefault("agent", "hlgo")
        print(json.dumps(payload, ensure_ascii=False))
        return

    if VALIDATE_RE.search(message):
        code, payload, _, stderr = run_json(
            [PY, f"{SCR}/hl_go_playwright_validate.py", "--json"],
            timeout=180,
        )
        if code != 0 and not payload.get("checks"):
            payload = {"ok": False, "whatsapp_reply": f"Playwright fallo: {stderr[-400:]}"}
        else:
            lines = [f"HL-Go QA — {'OK' if payload.get('ok') else 'FAIL'}"]
            for check in payload.get("checks") or []:
                mark = "OK" if check.get("ok") else "FAIL"
                lines.append(f"• {check.get('name')}: {mark}")
            payload["whatsapp_reply"] = "\n".join(lines)
        payload.setdefault("agent", "hlgo")
        print(json.dumps(payload, ensure_ascii=False))
        return

    if STATUS_RE.search(message):
        code, payload, _, _ = run_json([PY, f"{SCR}/hl_go_setup.py", "--json", "--skip-clone"], timeout=60)
        branch_name = current_branch() or "?"
        payload["whatsapp_reply"] = (
            f"HL-Go contexto\n"
            f"Repo: {payload.get('repo')}\n"
            f"Rama: {branch_name}\n"
            f"App: {payload.get('app')}\n"
            f"URL: http://localhost:8001\n"
            f"Comandos: /hl pull | /hl rama principal | /hl validar"
        )
        payload.setdefault("agent", "hlgo")
        print(json.dumps(payload, ensure_ascii=False))
        return

    if SUMMARY_RE.search(message):
        print(json.dumps(summarize_latest(), ensure_ascii=False))
        return

    agent_msg = message if message else "status HL-Go"
    code, reply, _, stderr = run_hl_agent(agent_msg, session_key)
    out = {
        "status": "ok" if code == 0 and reply else "error",
        "agent": "hlgo",
        "whatsapp_reply": reply or f"HL-Go sin respuesta. {stderr[-300:]}",
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
