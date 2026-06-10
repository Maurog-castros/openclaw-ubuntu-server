"""Delegate slash commands to Intel, with deterministic full daily radar."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent

PY = str(ROOT / ".venv-finanzas/bin/python")
if not Path(PY).exists():
    PY = "python3"
SCR = str(ROOT / "scripts")

CONSOLIDATED_RE = re.compile(
    r"\b(consolidad|consolidado|reporte\s+diario\s+consolidad|todas\s+las\s+fuentes)\b",
    re.I,
)
DAILY_RE = re.compile(r"\b(daily|radar|tendencias|intelligence report|que paso hoy|devops)\b", re.I)
GITHUB_SPECIFIC_RE = re.compile(r"\b(github|repo|repos|forks|estrellas|stars|actualizados|updated)\b", re.I)
LINKEDIN_RE = re.compile(r"\b(linkedin|innovaci[oó]n\s*radical|innovacionradical)\b", re.I)
YOUTUBE_URL_RE = re.compile(r"(?:youtube\.com|youtu\.be)", re.I)

if str(SCR) not in sys.path:
    sys.path.insert(0, str(SCR))
from intel_youtube import extract_video_id, load_active_session  # noqa: E402


def extract_text(payload: dict[str, Any]) -> str:
    for item in payload.get("payloads") or []:
        if isinstance(item, dict) and item.get("text"):
            return str(item["text"]).strip()
    return ""


def run_json(cmd: list[str], timeout: int = 300) -> tuple[int, dict[str, Any], str, str]:
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout, check=False)
    payload: dict[str, Any] = {}
    if proc.returncode == 0 and proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"whatsapp_reply": proc.stdout.strip()}
    return proc.returncode, payload, proc.stdout, proc.stderr


def run_consolidated(*, send_whatsapp: bool) -> dict[str, Any]:
    cmd = [PY, f"{SCR}/intel_consolidated_report.py", "--refresh", "--json"]
    if send_whatsapp:
        cmd.insert(-1, "--send-whatsapp")
    code, payload, stdout, stderr = run_json(cmd, timeout=300)
    if code != 0 or not payload.get("whatsapp_reply"):
        return {
            "status": "error",
            "agent": "intel",
            "whatsapp_reply": "Reporte consolidado fallo. Revisa logs/intel-consolidated.log",
            "stderr": stderr[-1200:],
            "stdout": stdout[-1200:],
        }
    payload.setdefault("agent", "intel")
    payload.setdefault("status", "ok")
    return payload


def run_daily() -> dict[str, Any]:
    code, payload, stdout, stderr = run_json([
        PY, f"{SCR}/intel_daily_messages.py", "--refresh", "--send-whatsapp", "--json",
    ], timeout=180)
    if code != 0:
        return {
            "status": "error",
            "agent": "intel",
            "whatsapp_reply": "Intel Daily fallo al refrescar fuentes.",
            "stderr": stderr[-1200:],
            "stdout": stdout[-1200:],
        }
    return payload


def run_youtube_summarize(url: str) -> dict[str, Any]:
    code, payload, stdout, stderr = run_json(
        [PY, f"{SCR}/intel_youtube.py", "--url", url, "--summarize", "--json"],
        timeout=300,
    )
    if code != 0 or not payload.get("whatsapp_reply"):
        return {
            "status": "error",
            "agent": "intel",
            "whatsapp_reply": "YouTube Intel: no pude resumir el video. Revisa subtitulos o logs.",
            "stderr": stderr[-1200:],
            "stdout": stdout[-1200:],
        }
    payload.setdefault("agent", "intel")
    payload.setdefault("status", "ok")
    return payload


def run_youtube_debate(text: str, video_id: str = "") -> dict[str, Any]:
    cmd = [PY, f"{SCR}/intel_youtube.py", "--debate", "--text", text, "--json"]
    if video_id:
        cmd.extend(["--video-id", video_id])
    code, payload, stdout, stderr = run_json(cmd, timeout=180)
    if code != 0 or not payload.get("whatsapp_reply"):
        return {
            "status": "error",
            "agent": "intel",
            "whatsapp_reply": "YouTube Intel: fallo el debate. Pasa el link de nuevo si expiro la sesion.",
            "stderr": stderr[-1200:],
            "stdout": stdout[-1200:],
        }
    payload.setdefault("agent", "intel")
    return payload


def run_linkedin_summary() -> dict[str, Any]:
    code, payload, stdout, stderr = run_json([PY, f"{SCR}/linkedin_intel_format.py", "--json"], timeout=60)
    if code != 0 or not payload:
        return {
            "status": "error",
            "agent": "intel",
            "whatsapp_reply": "LinkedIn Intel: no pude leer el ultimo scan.",
            "stderr": stderr[-800:],
        }
    payload.setdefault("agent", "intel")
    return payload


def run_intel(message: str, session_key: str) -> tuple[int, str, str, str]:
    cmd = [
        "openclaw", "agent", "--local", "--agent", "intel",
        "--session-key", session_key, "--message", message, "--json",
    ]
    code, payload, stdout, stderr = run_json(cmd, timeout=180)
    return code, extract_text(payload), stdout, stderr


def main() -> None:
    parser = argparse.ArgumentParser(description="Delegate to intel agent.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--session-key", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    message = args.text.strip()
    if message.lower().startswith("/intel"):
        message = message[6:].strip()
    if not message:
        message = "Dame un daily radar de tendencias con todas las fuentes."

    if CONSOLIDATED_RE.search(message):
        result = run_consolidated(send_whatsapp=True)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result.get("whatsapp_reply", ""))
        return

    if LINKEDIN_RE.search(message) and re.search(r"\bscan\b", message, re.I):
        result = run_consolidated(send_whatsapp=False)
        result["whatsapp_reply"] = (
            f"LinkedIn scan + consolidado refrescado. "
            f"Senales LinkedIn: {result.get('linkedin_signals', '?')}. "
            "Pide /intel reporte diario consolidado para ver insights."
        )
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["whatsapp_reply"])
        return

    if LINKEDIN_RE.search(message):
        result = run_linkedin_summary()
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result.get("whatsapp_reply", ""))
        return

    youtube_id = extract_video_id(message)
    if youtube_id or YOUTUBE_URL_RE.search(message):
        result = run_youtube_summarize(message)
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result.get("whatsapp_reply", ""))
        return

    active_yt = load_active_session()
    if active_yt and not CONSOLIDATED_RE.search(message):
        skip_debate = (
            LINKEDIN_RE.search(message)
            or (DAILY_RE.search(message) and not re.search(r"\b(video|youtube)\b", message, re.I))
        )
        if not skip_debate:
            result = run_youtube_debate(message, str(active_yt.get("video_id") or ""))
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result.get("whatsapp_reply", ""))
            return

    if DAILY_RE.search(message) and not (
        GITHUB_SPECIFIC_RE.search(message)
        and not re.search(r"\b(daily|radar|tendencias|intelligence)\b", message, re.I)
    ):
        result = run_daily()
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result.get("whatsapp_reply", ""))
        return

    session_key = args.session_key or f"agent:intel:whatsapp:{int(time.time())}"
    code, reply, stdout, stderr = run_intel(message, session_key)
    if code == 0 and not reply:
        code, reply, stdout, stderr = run_intel(
            "Responde en texto visible para WhatsApp. No uses herramientas. Solicitud original: " + message,
            session_key + ":retry",
        )

    if code != 0:
        result = {
            "status": "error",
            "agent": "intel",
            "stderr": stderr[-1200:],
            "stdout": stdout[-1200:],
            "whatsapp_reply": "Intel no pudo responder. Revisa logs del gateway/delegate.",
        }
    else:
        result = {
            "status": "ok" if reply else "empty",
            "agent": "intel",
            "session_key": session_key,
            "whatsapp_reply": reply or "Intel no genero texto visible.",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["whatsapp_reply"])


if __name__ == "__main__":
    main()
