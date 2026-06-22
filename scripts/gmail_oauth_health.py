#!/usr/bin/env python3
"""Health check Gmail OAuth: auto-sync legacy tokens y alerta WhatsApp."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from gmail_oauth_common import check_gmail_oauth_health
from runtime_paths import repo_root, secrets_dir

ROOT = repo_root()
STATE_PATH = ROOT / "data/gmail_oauth_health_state.json"
ALERT_COOLDOWN = timedelta(hours=12)


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def should_alert(state: dict) -> bool:
    last = state.get("last_alert_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    return datetime.now() - last_dt >= ALERT_COOLDOWN


def send_whatsapp(message: str) -> dict:
    target_file = secrets_dir() / "whatsapp_allow_from.txt"
    target = target_file.read_text(encoding="utf-8").strip() if target_file.exists() else ""
    if not target:
        return {"ok": False, "reason": "missing_whatsapp_target"}
    proc = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "openclaw-gateway",
            "openclaw",
            "message",
            "send",
            "--channel",
            "whatsapp",
            "--target",
            target,
            "--message",
            message,
            "--json",
        ],
        cwd=str(ROOT / "openclaw"),
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stderr": (proc.stderr or "").strip()[:300],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-alert", action="store_true")
    args = parser.parse_args()

    result = check_gmail_oauth_health()
    state = load_state()
    state["last_check_at"] = datetime.now().isoformat(timespec="seconds")
    state["last_result"] = result["status"]
    alerted = False

    if not result["healthy"] and not args.no_alert and should_alert(state):
        message = (
            "Gmail OAuth caido en openclaw-mauro.\n"
            f"workspace_ok={result['workspace_ok']} legacy_ok={result['legacy_ok']}\n"
            "Reautoriza en Ubuntu:\n"
            "cd /home/mauro/Dev/openclaw-mauro\n"
            ".venv-finanzas/bin/python scripts/google_workspace_oauth.py auth-url"
        )
        alert = send_whatsapp(message)
        result["alert"] = alert
        if alert.get("ok"):
            state["last_alert_at"] = datetime.now().isoformat(timespec="seconds")
            alerted = True

    state["last_alerted"] = alerted
    save_state(state)
    result["alerted"] = alerted

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"gmail-oauth-health: status={result['status']} "
            f"workspace={result['workspace_ok']} legacy={result['legacy_ok']} "
            f"synced={result['synced']} alerted={alerted}"
        )
    if not result["healthy"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
