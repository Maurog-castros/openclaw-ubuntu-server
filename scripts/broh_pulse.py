#!/usr/bin/env python3
"""Pulso proactivo /broh con frecuencia baja y horarios aleatorios."""
from __future__ import annotations

import argparse
import json
import random
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from broh_delegate import broh_data, build_perspective, truncate_broh
from vida_common import ROOT, now_local

COMPOSE_DIR = ROOT / "openclaw"
COMPOSE_FILES = ("docker-compose.yml", "docker-compose.finanzas-mounts.yml")
DEFAULT_TARGET = "+56945046845"
STATE_FILE = "pulse_state.json"
DEFAULT_WEEKLY_LIMIT = 2


def state_path() -> Path:
    return broh_data() / STATE_FILE


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def week_key(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def in_window(now: datetime, start_hour: int, end_hour: int) -> bool:
    return start_hour <= now.hour <= end_hour


def should_send(state: dict[str, Any], *, now: datetime, weekly_limit: int, chance: float, force: bool) -> bool:
    if force:
        return True
    current_week = week_key(now)
    sent = state.get("sent", {}) if state.get("week") == current_week else {}
    if len(sent) >= weekly_limit:
        return False
    today = now.strftime("%Y-%m-%d")
    if today in sent:
        return False
    return random.random() < chance


def build_message() -> str:
    base = build_perspective("pulso proactivo")
    return truncate_broh(base, max_len=500)


def send_whatsapp(message: str, target: str, *, dry_run: bool = False) -> dict[str, Any]:
    cmd = ["docker", "compose"]
    for compose_file in COMPOSE_FILES:
        cmd.extend(["-f", compose_file])
    cmd.extend(
        [
            "--project-directory",
            str(COMPOSE_DIR),
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
        ]
    )
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, cwd=str(COMPOSE_DIR), text=True, capture_output=True, timeout=60, check=False)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-1200:],
        "stderr": proc.stderr[-1200:],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Broh proactive pulse.")
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--start-hour", type=int, default=10)
    parser.add_argument("--end-hour", type=int, default=21)
    parser.add_argument("--weekly-limit", type=int, default=DEFAULT_WEEKLY_LIMIT)
    parser.add_argument("--chance", type=float, default=0.16)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    now = now_local()
    state = load_state()
    if not args.force and not in_window(now, args.start_hour, args.end_hour):
        out = {"status": "skip", "reason": "outside_window", "now": now.isoformat()}
    elif not should_send(
        state,
        now=now,
        weekly_limit=max(1, args.weekly_limit),
        chance=max(0.0, min(1.0, args.chance)),
        force=args.force,
    ):
        out = {"status": "skip", "reason": "not_due", "now": now.isoformat(), "week": week_key(now)}
    else:
        message = build_message()
        sent = send_whatsapp(message, args.target, dry_run=args.dry_run)
        if sent["ok"]:
            if not args.dry_run:
                current_week = week_key(now)
                if state.get("week") != current_week:
                    state = {"week": current_week, "sent": {}}
                state.setdefault("sent", {})[now.strftime("%Y-%m-%d")] = now.isoformat(timespec="seconds")
                state["last_target"] = args.target
                save_state(state)
            out = {"status": "ok", "agent": "broh", "message": message, "send": sent}
        else:
            out = {"status": "error", "agent": "broh", "message": message, "send": sent}

    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out.get("message", out["reason"]))


if __name__ == "__main__":
    main()
