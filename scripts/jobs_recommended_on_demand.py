#!/usr/bin/env python3
"""Ejecuta Jobs on demand y reporta progreso por WhatsApp."""
from __future__ import annotations

import fcntl
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from jobs_daily_auto import OPENCLAW_DIR, resolve_target_file
from jobs_recommended_digest import build

ROOT = Path(__file__).resolve().parent.parent
SCR = ROOT / "scripts"
LINKEDIN_PY = ROOT / ".venv-linkedin-intel/bin/python"
PY = ROOT / ".venv-finanzas/bin/python"
LOG = ROOT / "runtime/logs/jobs-recommended-on-demand.log"
LOCK = Path("/tmp/openclaw-jobs-recommended-on-demand.lock")


def progress_percent(start: int, end: int, elapsed: float, estimate: float) -> int:
    span = max(1, end - start)
    fraction = min(0.98, max(0.0, elapsed / max(1.0, estimate)))
    return min(end - 1, start + max(1, int(span * fraction)))


def start_notification(target_file: Path, message: str) -> subprocess.Popen:
    target = target_file.read_text(encoding="utf-8").strip().splitlines()[0]
    if len(message) > 3800:
        message = message[:3700].rstrip() + "\n\n(Truncado; ver CSV local.)"
    cmd = [
        "docker", "compose", "-f", "docker-compose.yml",
        "-f", "docker-compose.finanzas-mounts.yml",
        "exec", "-T", "openclaw-gateway",
        "openclaw", "message", "send",
        "--channel", "whatsapp",
        "--target", target,
        "--message", message,
        "--json",
    ]
    return subprocess.Popen(
        cmd,
        cwd=str(OPENCLAW_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class ProgressNotifier:
    """Mantiene un solo envío activo y conserva solo el avance más reciente."""

    def __init__(self, target_file: Path):
        self.target_file = target_file
        self.proc: subprocess.Popen | None = None
        self.pending = ""

    def offer(self, message: str) -> None:
        self.pending = message
        self.pump()

    def pump(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            return
        self.proc = None
        if self.pending:
            message, self.pending = self.pending, ""
            self.proc = start_notification(self.target_file, message)

    def flush(self, timeout: float = 180) -> None:
        deadline = time.monotonic() + timeout
        while (self.pending or (self.proc is not None and self.proc.poll() is None)) and time.monotonic() < deadline:
            self.pump()
            time.sleep(1)
        self.pump()


def run_step(
    cmd: list[str],
    *,
    notifier: ProgressNotifier,
    label: str,
    start: int,
    end: int,
    estimate: float,
) -> int:
    started = time.monotonic()
    with LOG.open("a", encoding="utf-8") as handle:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )
        while proc.poll() is None:
            time.sleep(5)
            pct = progress_percent(start, end, time.monotonic() - started, estimate)
            notifier.offer(f"Jobs {pct}% — {label}")
    if proc.returncode == 0:
        notifier.offer(f"Jobs {end}% — {label} completado")
    return int(proc.returncode or 0)


def main() -> int:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0

        target = resolve_target_file()
        if not target:
            print("Falta whatsapp_allow_from.txt", flush=True)
            return 1

        time.sleep(2)
        notifier = ProgressNotifier(target)
        notifier.offer("Jobs 0% — iniciando búsqueda")

        if run_step(
            [str(LINKEDIN_PY), str(SCR / "jobs_linkedin_recommended.py"), "--json"],
            notifier=notifier, label="buscando en LinkedIn", start=0, end=20, estimate=25,
        ) != 0:
            notifier.offer("Jobs detenido: falló la búsqueda en LinkedIn.")
            notifier.flush()
            return 1

        chile_cmd = [str(LINKEDIN_PY), str(SCR / "jobs_chiletrabajos_scrape.py"), "--json"]
        chile_code = run_step(
            chile_cmd,
            notifier=notifier, label="buscando en ChileTrabajos", start=20, end=35, estimate=25,
        )
        if chile_code != 0:
            chile_code = run_step(
                [*chile_cmd[:-1], "--no-session", "--json"],
                notifier=notifier, label="reintentando ChileTrabajos", start=34, end=35, estimate=20,
            )
        if chile_code != 0:
            notifier.offer("Jobs 35% — ChileTrabajos no disponible; continuaré con LinkedIn")

        if run_step(
            [str(LINKEDIN_PY), str(SCR / "jobs_recommended_pipeline.py"), "--json"],
            notifier=notifier, label="verificando y evaluando vacantes", start=35, end=95, estimate=150,
        ) != 0:
            notifier.offer("Jobs detenido: falló la verificación de vacantes.")
            notifier.flush()
            return 1

        message, rows = build()
        notifier.offer("Jobs 100% — reporte listo")
        notifier.flush()
        notifier.offer(message)
        notifier.flush()
        print(f"[{datetime.now().astimezone().isoformat()}] completed rows={len(rows)}", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
