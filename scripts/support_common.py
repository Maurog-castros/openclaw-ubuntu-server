"""Utilidades agente soporte OpenClaw (/supp)."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path("/home/mauro/openclaw-mauro")
if not REPO_ROOT.exists():
    REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_FINDINGS_CSV = REPO_ROOT / "data/support_findings.csv"
DEFAULT_SQLITE = REPO_ROOT / "data/config/state/openclaw.sqlite"
DEFAULT_SESSIONS_JSON = REPO_ROOT / "data/config/agents/finanzas/sessions/sessions.json"
GATEWAY_CONTAINER = "openclaw-openclaw-gateway-1"
OPENCLAW_LOG_GLOB = "/tmp/openclaw/openclaw-*.log"

FINDINGS_COLUMNS = [
    "finding_id",
    "detected_at",
    "severity",
    "category",
    "source_log",
    "summary",
    "detail",
    "status",
    "remediated_at",
    "remediation_action",
    "verified_at",
    "commit_hash",
]

AUTO_FIX_CATEGORIES = frozenset(
    {
        "session_stuck",
        "context_overflow",
        "session_heavy",
        "whatsapp_pending",
        "gateway_unhealthy",
        "bootstrap_budget",
    }
)

FIXABLE_STATUSES = frozenset({"open", "failed"})

FIN_IDENTITY_PATH = REPO_ROOT / "data/workspace/marketing/finanzas/IDENTITY.md"
FIN_SESSIONS_DIR = REPO_ROOT / "data/config/agents/finanzas/sessions"
SESSION_HEAVY_MIN_LINES = 40
SESSION_HEAVY_MIN_BYTES = 400_000
RECENT_RESET_MINUTES = 15
GATEWAY_HEALTH_WAIT_SEC = 65
GATEWAY_HEALTH_POLL_SEC = 5
MAX_BOOTSTRAP_IDENTITY_CHARS = 400

LOG_DEDUP_CATEGORIES = frozenset({"context_overflow", "session_stuck", "session_heavy"})
FIN_RESET_CLOSE_CATEGORIES = frozenset(
    {"context_overflow", "session_stuck", "session_heavy", "whatsapp_pending"}
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def run_cmd(cmd: List[str], *, timeout: int = 120, cwd: Optional[Path] = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def docker_logs(tail: int = 200) -> str:
    code, out, err = run_cmd(["docker", "logs", GATEWAY_CONTAINER, "--tail", str(tail)], timeout=60)
    return out + err if code == 0 else err or out


def docker_exec_tail_log(lines: int = 300) -> str:
    code, out, err = run_cmd(
        [
            "docker",
            "exec",
            GATEWAY_CONTAINER,
            "sh",
            "-c",
            f"tail -n {lines} {OPENCLAW_LOG_GLOB} 2>/dev/null || true",
        ],
        timeout=60,
    )
    return out or err


def gateway_healthy() -> bool:
    code, out, _ = run_cmd(
        [
            "docker",
            "inspect",
            GATEWAY_CONTAINER,
            "--format",
            "{{.State.Health.Status}}",
        ],
        timeout=30,
    )
    return code == 0 and "healthy" in (out or "").lower()


def whatsapp_pending_count() -> int:
    if not DEFAULT_SQLITE.exists():
        return 0
    import sqlite3

    con = sqlite3.connect(DEFAULT_SQLITE)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT count(*) FROM plugin_state_entries "
            "WHERE plugin_id='whatsapp' AND namespace LIKE 'inbound.v1.pending%'"
        )
        row = cur.fetchone()
        return int(row[0] or 0) if row else 0
    finally:
        con.close()


def fin_failed_delivery_count() -> int:
    if not DEFAULT_SQLITE.exists():
        return 0
    import sqlite3

    con = sqlite3.connect(DEFAULT_SQLITE)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT count(*) FROM delivery_queue_entries "
            "WHERE status='failed' AND (session_key LIKE 'agent:fin%' OR session_key LIKE 'agent:finanzas%')"
        )
        row = cur.fetchone()
        return int(row[0] or 0) if row else 0
    finally:
        con.close()


FIN_SESSION_KEYS = [
    "agent:fin:whatsapp:default:direct:+56945046845",
    "agent:fin:main",
    "agent:finanzas:whatsapp:default:direct:+56945046845",
    "agent:finanzas:main",
]


def clear_whatsapp_pending_and_reset_sessions(*, restart_gateway: bool = True) -> Dict[str, Any]:
    """Limpia cola WA + sesiones fin (Python puro; no depende de bash CRLF)."""
    import shutil
    import sqlite3
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    pending_deleted = 0
    failed_deleted = 0
    sessions_removed: List[str] = []

    if DEFAULT_SQLITE.exists():
        backup = DEFAULT_SQLITE.with_name(f"{DEFAULT_SQLITE.name}.bak-clear-{stamp}")
        shutil.copy2(DEFAULT_SQLITE, backup)
        con = sqlite3.connect(DEFAULT_SQLITE)
        try:
            cur = con.cursor()
            cur.execute(
                "DELETE FROM plugin_state_entries "
                "WHERE plugin_id='whatsapp' AND namespace LIKE 'inbound.v1.pending%'"
            )
            pending_deleted = cur.rowcount
            cur.execute(
                "DELETE FROM delivery_queue_entries WHERE status='failed' "
                "AND (session_key LIKE 'agent:fin%' OR session_key LIKE 'agent:finanzas%')"
            )
            failed_deleted = cur.rowcount
            con.commit()
        finally:
            con.close()

    if DEFAULT_SESSIONS_JSON.exists():
        backup = DEFAULT_SESSIONS_JSON.with_suffix(f".json.bak-reset-{stamp}")
        shutil.copy2(DEFAULT_SESSIONS_JSON, backup)
        data = json.loads(DEFAULT_SESSIONS_JSON.read_text(encoding="utf-8"))
        sessions_base = DEFAULT_SESSIONS_JSON.parent
        for key in FIN_SESSION_KEYS:
            entry = data.pop(key, None)
            if not entry:
                continue
            sessions_removed.append(key)
            sid = entry.get("sessionId") or ""
            for pattern in (f"{sid}.jsonl", f"{sid}.trajectory.jsonl", f"{sid}.trajectory-path.json"):
                if sid:
                    path = sessions_base / pattern
                    if path.exists():
                        path.rename(path.with_name(path.name + f".bak-reset-{stamp}"))
        DEFAULT_SESSIONS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    restart_msg = ""
    if restart_gateway:
        code, out, err = run_cmd(
            [
                "docker",
                "compose",
                "-f",
                "docker-compose.yml",
                "-f",
                "docker-compose.finanzas-mounts.yml",
                "restart",
                "openclaw-gateway",
            ],
            cwd=REPO_ROOT / "openclaw",
            timeout=120,
        )
        restart_msg = (out or err or f"exit={code}")[:200]
        if wait_gateway_healthy():
            restart_msg += " | gateway healthy tras espera"
        else:
            restart_msg += " | gateway aun no healthy tras espera"

    return {
        "pending_deleted": pending_deleted,
        "failed_deleted": failed_deleted,
        "sessions_removed": sessions_removed,
        "restart": restart_msg,
    }


def wait_gateway_healthy(*, timeout_sec: int = GATEWAY_HEALTH_WAIT_SEC, poll_sec: int = GATEWAY_HEALTH_POLL_SEC) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if gateway_healthy():
            return True
        time.sleep(poll_sec)
    return gateway_healthy()


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def had_recent_fin_reset(*, minutes: int = RECENT_RESET_MINUTES) -> bool:
    cutoff = datetime.now(timezone.utc).astimezone() - timedelta(minutes=minutes)
    if FIN_SESSIONS_DIR.exists():
        for bak in FIN_SESSIONS_DIR.glob("sessions.json.bak-reset-*"):
            if datetime.fromtimestamp(bak.stat().st_mtime, tz=cutoff.tzinfo) >= cutoff:
                return True
    for row in load_findings():
        if row.get("category") not in FIN_RESET_CLOSE_CATEGORIES:
            continue
        if row.get("status") != "remediated":
            continue
        remediated = _parse_iso(row.get("remediated_at") or "")
        if remediated and remediated >= cutoff:
            return True
    return False


def fin_main_session_entry() -> Dict[str, Any]:
    if not DEFAULT_SESSIONS_JSON.exists():
        return {}
    try:
        data = json.loads(DEFAULT_SESSIONS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data.get("agent:fin:main") or data.get("agent:finanzas:main") or {}


def fin_session_jsonl_stats() -> Dict[str, Any]:
    entry = fin_main_session_entry()
    sid = entry.get("sessionId") or ""
    if not sid:
        return {"line_count": 0, "bytes": 0, "path": None}
    path = FIN_SESSIONS_DIR / f"{sid}.jsonl"
    if not path.exists():
        return {"line_count": 0, "bytes": 0, "path": str(path)}
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return {"line_count": len(lines), "bytes": path.stat().st_size, "path": str(path)}


def detect_session_heavy() -> Optional[Dict[str, str]]:
    entry = fin_main_session_entry()
    if not entry:
        return None
    stats = fin_session_jsonl_stats()
    if stats["line_count"] < SESSION_HEAVY_MIN_LINES and stats["bytes"] < SESSION_HEAVY_MIN_BYTES:
        return None
    return {
        "severity": "critical",
        "category": "session_heavy",
        "source_log": "sessions.jsonl",
        "summary": "Sesion agent:fin:main muy cargada (preventivo)",
        "detail": (
            f"lines={stats['line_count']} bytes={stats['bytes']} "
            f"umbral>={SESSION_HEAVY_MIN_LINES}l/{SESSION_HEAVY_MIN_BYTES}b"
        ),
    }


def filter_detected_findings(detected: List[Dict[str, str]]) -> List[Dict[str, str]]:
    if not detected:
        return detected
    recent_reset = had_recent_fin_reset()
    fin_entry = fin_main_session_entry()
    fin_active = bool(fin_entry)
    fin_running = (fin_entry.get("status") or "") == "running"
    out: List[Dict[str, str]] = []
    for item in detected:
        cat = item.get("category") or ""
        source = item.get("source_log") or ""
        if recent_reset and cat in LOG_DEDUP_CATEGORIES:
            continue
        if cat == "context_overflow" and source == "openclaw-gateway" and not fin_active:
            continue
        if cat == "session_stuck" and source == "openclaw-gateway" and not fin_running:
            continue
        out.append(item)
    return out


def bootstrap_budget_ok() -> bool:
    if not FIN_IDENTITY_PATH.exists():
        return True
    return len(FIN_IDENTITY_PATH.read_text(encoding="utf-8")) <= MAX_BOOTSTRAP_IDENTITY_CHARS


def remediate_bootstrap_budget() -> str:
    path = FIN_IDENTITY_PATH
    if not path.exists():
        return "IDENTITY.md no encontrado"
    original = path.read_text(encoding="utf-8")
    if len(original) <= MAX_BOOTSTRAP_IDENTITY_CHARS:
        return f"IDENTITY.md OK ({len(original)} chars)"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-supp-{stamp}")
    backup.write_text(original, encoding="utf-8")
    suffix = f"\n\n_(truncado /supp {stamp})_\n"
    budget = MAX_BOOTSTRAP_IDENTITY_CHARS - len(suffix)
    trimmed = original[:budget].rstrip() + suffix
    path.write_text(trimmed, encoding="utf-8")
    return f"IDENTITY.md {len(original)} -> {len(trimmed)} chars (backup {backup.name})"


def mark_category_findings_remediated(
    categories: frozenset[str] | set[str],
    *,
    action: str,
    commit_hash: str = "",
) -> int:
    rows = load_findings()
    changed = 0
    stamp = now_iso()
    for row in rows:
        if row.get("category") not in categories:
            continue
        if row.get("status") not in FIXABLE_STATUSES:
            continue
        row["status"] = "remediated"
        row["remediated_at"] = stamp
        row["remediation_action"] = action[:500]
        row["verified_at"] = stamp
        if commit_hash:
            row["commit_hash"] = commit_hash[:64]
        changed += 1
    if changed:
        with DEFAULT_FINDINGS_CSV.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FINDINGS_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    return changed


def live_health() -> Dict[str, Any]:
    sess = fin_main_session_status()
    pending = whatsapp_pending_count()
    failed_del = fin_failed_delivery_count()
    healthy = gateway_healthy()
    session_running = (sess.get("status") or "") == "running"
    heavy = detect_session_heavy()
    needs_fix = (
        not healthy
        or pending > 0
        or session_running
        or failed_del > 0
        or heavy is not None
    )
    return {
        "gateway_healthy": healthy,
        "whatsapp_pending": pending,
        "fin_session": sess,
        "fin_session_running": session_running,
        "fin_failed_deliveries": failed_del,
        "fin_session_heavy": heavy,
        "needs_remediation": needs_fix,
    }


def fin_main_session_status() -> Dict[str, Any]:
    if not DEFAULT_SESSIONS_JSON.exists():
        return {}
    try:
        data = json.loads(DEFAULT_SESSIONS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    entry = data.get("agent:fin:main") or {}
    return {
        "status": entry.get("status"),
        "session_id": entry.get("sessionId"),
        "updated_at": entry.get("updatedAt") or entry.get("updated_at"),
    }


def finding_fingerprint(category: str, summary: str) -> str:
    raw = f"{category}|{summary}"[:500]
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def ensure_findings_csv(path: Path = DEFAULT_FINDINGS_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=FINDINGS_COLUMNS).writeheader()


def load_findings(path: Path = DEFAULT_FINDINGS_CSV) -> List[Dict[str, str]]:
    ensure_findings_csv(path)
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def append_finding(row: Dict[str, Any], path: Path = DEFAULT_FINDINGS_CSV) -> Dict[str, str]:
    ensure_findings_csv(path)
    entry = {col: str(row.get(col) or "") for col in FINDINGS_COLUMNS}
    if not entry["finding_id"]:
        entry["finding_id"] = uuid.uuid4().hex[:12]
    if not entry["detected_at"]:
        entry["detected_at"] = now_iso()
    if not entry["status"]:
        entry["status"] = "open"

    existing = load_findings(path)
    fp = finding_fingerprint(entry["category"], entry["summary"])
    for old in existing:
        if old.get("status") in FIXABLE_STATUSES and finding_fingerprint(
            old.get("category", ""), old.get("summary", "")
        ) == fp:
            return old

    with path.open("a", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=FINDINGS_COLUMNS).writerow(entry)
    return entry


def reopen_failed_findings(categories: Optional[List[str]] = None, path: Path = DEFAULT_FINDINGS_CSV) -> int:
    """Marca failed -> open para permitir reintento de auto-fix."""
    rows = load_findings(path)
    changed = 0
    for row in rows:
        if row.get("status") != "failed":
            continue
        cat = row.get("category") or ""
        if categories and cat not in categories:
            continue
        if cat not in AUTO_FIX_CATEGORIES:
            continue
        row["status"] = "open"
        changed += 1
    if changed:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FINDINGS_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    return changed


def update_finding(
    finding_id: str,
    updates: Dict[str, str],
    path: Path = DEFAULT_FINDINGS_CSV,
) -> Optional[Dict[str, str]]:
    rows = load_findings(path)
    changed = False
    for row in rows:
        if row.get("finding_id") == finding_id:
            row.update({k: str(v) for k, v in updates.items()})
            changed = True
            break
    if not changed:
        return None
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FINDINGS_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return next(r for r in rows if r.get("finding_id") == finding_id)


def parse_log_findings(log_text: str) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    if re.search(r"stalled session:.*agent:fin:main", log_text):
        findings.append(
            {
                "severity": "critical",
                "category": "session_stuck",
                "source_log": "openclaw-gateway",
                "summary": "Sesion agent:fin:main atascada (stalled_agent_run)",
                "detail": "queueDepth>0 sin progreso LLM",
            }
        )
    if "context-overflow-precheck" in log_text:
        findings.append(
            {
                "severity": "critical",
                "category": "context_overflow",
                "source_log": "openclaw-gateway",
                "summary": "Context overflow en agent:fin:main",
                "detail": "Historial/tool results exceden ventana; requiere reset sesion",
            }
        )
    if "Ollama could not be reached" in log_text:
        findings.append(
            {
                "severity": "info",
                "category": "ollama_unreachable",
                "source_log": "openclaw-gateway",
                "summary": "Ollama 127.0.0.1:11434 no alcanzable",
                "detail": "Vision local fallo; remoto LiteLLM puede seguir OK",
            }
        )
    if "remaining bootstrap budget is 1 chars" in log_text:
        findings.append(
            {
                "severity": "warning",
                "category": "bootstrap_budget",
                "source_log": "openclaw-gateway",
                "summary": "SOUL/USER truncado por budget bootstrap",
                "detail": "Reducir SOUL o USER.md para agente fin",
            }
        )
    return findings


def git_commit_push(message: str) -> Dict[str, str]:
    run_cmd(["git", "add", "data/support_findings.csv", "scripts/"])
    code, out, err = run_cmd(["git", "commit", "-m", message], timeout=60)
    if code != 0 and "nothing to commit" in (out + err):
        return {"status": "skip", "message": "sin cambios para commit"}
    if code != 0:
        return {"status": "error", "message": (err or out)[:500]}
    _, log_out, _ = run_cmd(["git", "log", "-1", "--format=%H %s"])
    hash_line = (log_out or "").strip()
    push_code, push_out, push_err = run_cmd(["git", "push"], timeout=120)
    if push_code != 0:
        return {"status": "committed_no_push", "message": (push_err or push_out)[:500], "commit": hash_line}
    return {"status": "ok", "commit": hash_line, "message": "push ok"}
