"""Proactive daily /care check-in with diary context."""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from vida_common import ROOT, care_data, now_local, reply, truncate_whatsapp

COMPOSE_DIR = ROOT / "openclaw"
COMPOSE_FILES = ("docker-compose.yml", "docker-compose.finanzas-mounts.yml")
DEFAULT_TARGET = "+56945046845"
STATE_FILE = "daily_prompt_state.json"
MIN_DIARY_CHARS = 12
DEFAULT_DAILY_LIMIT = 2
DEFAULT_INTERVAL_MINUTES = 15


def state_path() -> Path:
    return care_data() / STATE_FILE


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


def normalize_entry(line: str) -> str:
    text = re.sub(r"^\s*-\s*\[\d{2}:\d{2}\]\s*", "", line).strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -")


def useful_entry(text: str) -> bool:
    lower = text.lower().strip()
    if len(lower) < MIN_DIARY_CHARS:
        return False
    if lower in {"diario", "anota en diario", "guardalo en diario"}:
        return False
    return True


def recent_diary_entry(days: int = 7) -> tuple[str, str] | None:
    base = care_data() / "diary"
    today = now_local().date()
    for offset in range(days):
        day = today - timedelta(days=offset)
        path = base / f"{day:%Y-%m-%d}.md"
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for raw in reversed(lines):
            text = normalize_entry(raw)
            if useful_entry(text):
                return f"{day:%Y-%m-%d}", text
    return None


def build_message(slot: int) -> str:
    found = recent_diary_entry()
    intro = f"Fede /care {slot}/{DEFAULT_DAILY_LIMIT}:"
    if found:
        day, entry = found
        if day == now_local().strftime("%Y-%m-%d"):
            when = "hoy"
        else:
            when = f"el {day}"
        return truncate_whatsapp(
            f"{intro} me quedé con esto que anotaste {when}: \"{entry}\". "
            "No resuelve todo, pero es evidencia de que sigues cuidándote. "
            "Acción chica: 2 min de pausa. ¿Ánimo 0-10?",
            max_len=420,
        )
    return truncate_whatsapp(
        f"{intro} paso a acompañarte un momento. No necesitas resolver todo hoy; "
        "solo cerrar el día un poco mejor que como empezó. ¿Ánimo 0-10?",
        max_len=420,
    )


def in_window(now: datetime, start_hour: int, end_hour: int) -> bool:
    return start_hour <= now.hour <= end_hour


def minutes_since_midnight(value: datetime) -> int:
    return value.hour * 60 + value.minute


def format_slot(minute_of_day: int) -> str:
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def today_plan(
    state: dict[str, Any],
    *,
    day: str,
    start_hour: int,
    end_hour: int,
    daily_limit: int,
    interval_minutes: int,
) -> list[int]:
    plan = state.get("plan") if state.get("plan_day") == day else None
    if isinstance(plan, list) and len(plan) == daily_limit:
        try:
            return sorted(int(item) for item in plan)
        except (TypeError, ValueError):
            pass

    start = start_hour * 60
    end = end_hour * 60
    slots = list(range(start, end + 1, interval_minutes))
    if daily_limit >= len(slots):
        selected = slots
    else:
        # Keep prompts spread through the day instead of clustering by chance.
        midpoint = len(slots) // 2
        first_pool = slots[:midpoint] or slots
        second_pool = slots[midpoint:] or slots
        selected = [random.choice(first_pool), random.choice(second_pool)]
        while len(set(selected)) < daily_limit:
            selected = random.sample(slots, daily_limit)
    state["plan_day"] = day
    state["plan"] = sorted(selected)
    state["sent_slots"] = []
    save_state(state)
    return sorted(selected)


def due_slot(state: dict[str, Any], plan: list[int], now: datetime, *, interval_minutes: int) -> int | None:
    sent = {int(item) for item in state.get("sent_slots", []) if str(item).isdigit()}
    current = minutes_since_midnight(now)
    for slot in plan:
        if slot in sent:
            continue
        if slot <= current < slot + interval_minutes:
            return slot
    return None


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
    proc = subprocess.run(
        cmd,
        cwd=str(COMPOSE_DIR),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-1200:],
        "stderr": proc.stderr[-1200:],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Daily proactive /care WhatsApp prompt.")
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--start-hour", type=int, default=9)
    ap.add_argument("--end-hour", type=int, default=20)
    ap.add_argument("--daily-limit", type=int, default=DEFAULT_DAILY_LIMIT)
    ap.add_argument("--interval-minutes", type=int, default=DEFAULT_INTERVAL_MINUTES)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    now = now_local()
    today = now.strftime("%Y-%m-%d")
    state = load_state()
    daily_limit = max(1, int(args.daily_limit))
    interval_minutes = max(5, int(args.interval_minutes))

    if not args.force and not in_window(now, args.start_hour, args.end_hour):
        out = {"status": "skip", "reason": "outside_window", "now": now.isoformat()}
    else:
        plan = today_plan(
            state,
            day=today,
            start_hour=args.start_hour,
            end_hour=args.end_hour,
            daily_limit=daily_limit,
            interval_minutes=interval_minutes,
        )
        slot = plan[0] if args.force else due_slot(state, plan, now, interval_minutes=interval_minutes)
        if slot is None:
            out = {
                "status": "skip",
                "reason": "not_due",
                "now": now.isoformat(),
                "plan": [format_slot(item) for item in plan],
                "sent": [format_slot(int(item)) for item in state.get("sent_slots", [])],
            }
            print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["reason"])
            return
        message = build_message(plan.index(slot) + 1)
        send_result = send_whatsapp(message, args.target, dry_run=args.dry_run)
        if send_result["ok"]:
            if not args.dry_run:
                sent_slots = {int(item) for item in state.get("sent_slots", []) if str(item).isdigit()}
                sent_slots.add(slot)
                state["sent_slots"] = sorted(sent_slots)
                state["last_sent_at"] = now.isoformat()
                state["last_target"] = args.target
                save_state(state)
            out = reply(
                "Check-in Care enviado.",
                message=message,
                slot=format_slot(slot),
                plan=[format_slot(item) for item in plan],
                send=send_result,
            )
        else:
            out = {
                "status": "error",
                "whatsapp_reply": "No pude enviar el check-in /care.",
                "message": message,
                "send": send_result,
            }

    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
