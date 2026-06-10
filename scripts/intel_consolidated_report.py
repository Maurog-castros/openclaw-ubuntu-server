"""Reporte diario consolidado: HN + Reddit + GitHub + LinkedIn, opcional WhatsApp."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from intel_daily_report import (
    RAW,
    ROOT,
    build_report,
    format_whatsapp,
    load_linkedin_signals,
    refresh_sources,
)
from datetime import date

INTEL_WS = ROOT / "data/workspace/marketing/intel"
REPORTS = INTEL_WS / "reports"
DEFAULT_TARGET_FILE = Path("/home/node/.openclaw-secrets/whatsapp_allow_from.txt")


def truncate_message(message: str, limit: int = 3900) -> str:
    message = message.strip()
    if len(message) <= limit:
        return message
    return message[: limit - 80].rstrip() + "\n\n(Truncado; ver reporte consolidado local.)"


def send_whatsapp(message: str, target_file: str) -> dict[str, object]:
    target = Path(target_file).read_text(encoding="utf-8").strip().splitlines()[0]
    proc = subprocess.run(
        [
            "openclaw", "message", "send",
            "--channel", "whatsapp",
            "--target", target,
            "--message", truncate_message(message),
            "--json",
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    return {"ok": proc.returncode == 0, "stdout": proc.stdout[-800:], "stderr": proc.stderr[-800:]}


def maybe_refresh_linkedin(refresh: bool) -> None:
    if not refresh:
        return
    scout = ROOT / "scripts/linkedin_intel_scout.py"
    venv_py = ROOT / ".venv-linkedin-intel/bin/python"
    win_py = ROOT / ".venv-linkedin-intel/Scripts/python.exe"
    py = venv_py if venv_py.exists() else (win_py if win_py.exists() else None)
    if py and scout.exists():
        subprocess.run([str(py), str(scout), "scan"], cwd=str(ROOT), timeout=600, check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Intel consolidated daily report")
    parser.add_argument("--refresh", action="store_true", help="Refrescar HN/Reddit/GitHub (+ LinkedIn si hay venv)")
    parser.add_argument("--refresh-linkedin-only", action="store_true")
    parser.add_argument("--send-whatsapp", action="store_true")
    parser.add_argument("--target-file", default=str(DEFAULT_TARGET_FILE))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.refresh_linkedin_only:
        maybe_refresh_linkedin(True)
        return

    if args.refresh or not RAW.exists():
        refresh_sources()
    maybe_refresh_linkedin(args.refresh)

    raw = RAW.read_text(encoding="utf-8", errors="ignore") if RAW.exists() else ""
    linkedin = load_linkedin_signals()
    report = build_report(raw, linkedin)
    whatsapp = format_whatsapp(report)

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{date.today().isoformat()}-consolidated.md"
    out.write_text(report + "\n", encoding="utf-8")

    payload: dict[str, object] = {
        "status": "ok",
        "agent": "intel",
        "report_file": str(out),
        "linkedin_signals": len(linkedin),
        "whatsapp_reply": whatsapp,
    }

    if args.send_whatsapp:
        sent = send_whatsapp(whatsapp, args.target_file)
        payload["sent"] = sent
        if not sent.get("ok"):
            payload["status"] = "error"
            payload["whatsapp_reply"] = "Consolidado generado pero fallo envio WhatsApp."

    if args.json:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(whatsapp)


if __name__ == "__main__":
    main()
