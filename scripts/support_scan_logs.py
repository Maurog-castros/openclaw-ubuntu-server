#!/usr/bin/env python3
"""Escanea logs OpenClaw y registra hallazgos en CSV."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from support_common import (
    GATEWAY_CONTAINER,
    append_finding,
    detect_session_heavy,
    docker_exec_tail_log,
    docker_logs,
    filter_detected_findings,
    fin_failed_delivery_count,
    fin_main_session_status,
    gateway_healthy,
    live_health,
    load_findings,
    parse_log_findings,
    reopen_failed_findings,
    whatsapp_pending_count,
)


def scan() -> dict:
    log_blob = docker_logs(250) + "\n" + docker_exec_tail_log(200)
    detected = parse_log_findings(log_blob)

    heavy = detect_session_heavy()
    if heavy:
        detected.append(heavy)

    pending = whatsapp_pending_count()
    if pending > 0:
        detected.append(
            {
                "severity": "warning",
                "category": "whatsapp_pending",
                "source_log": "openclaw.sqlite",
                "summary": f"Cola WhatsApp pending: {pending} mensaje(s)",
                "detail": "inbound.v1.pending en plugin_state_entries",
            }
        )

    if not gateway_healthy():
        detected.append(
            {
                "severity": "critical",
                "category": "gateway_unhealthy",
                "source_log": "docker",
                "summary": "Gateway no healthy",
                "detail": GATEWAY_CONTAINER,
            }
        )

    sess = fin_main_session_status()
    if sess.get("status") == "running":
        detected.append(
            {
                "severity": "critical",
                "category": "session_stuck",
                "source_log": "sessions.json",
                "summary": "agent:fin:main en estado running",
                "detail": f"sessionId={sess.get('session_id', '')[:20]}",
            }
        )

    detected = filter_detected_findings(detected)

    if detected:
        reopen_failed_findings()
    saved = [append_finding(item) for item in detected]
    open_count = sum(1 for r in load_findings() if r.get("status") in {"open", "failed"})
    health = live_health()

    lines = [
        f"Scan: {len(saved)} hallazgo(s) nuevos/actualizados",
        f"Abiertos/reintentables en CSV: {open_count}",
        f"Gateway: {'healthy' if health.get('gateway_healthy') else 'NO healthy'}",
        f"WhatsApp pending: {health.get('whatsapp_pending', pending)}",
        f"Sesion fin: {health.get('fin_session', {}).get('status', '?')}",
        f"Entregas failed fin: {health.get('fin_failed_deliveries', 0)}",
    ]
    if health.get("needs_remediation"):
        lines.append("Accion sugerida: /supp fix o menu 2 (Auto-fix)")
    for row in saved[:5]:
        lines.append(f"• [{row.get('severity')}] {row.get('category')}: {row.get('summary')}")

    summary = "\n".join(lines)
    return {
        "status": "ok",
        "new_findings": len(saved),
        "open_findings": open_count,
        "findings": saved,
        "gateway_healthy": gateway_healthy(),
        "whatsapp_pending": pending,
        "fin_session": sess,
        "summary": summary,
        "whatsapp_reply": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan logs OpenClaw -> support_findings.csv")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = scan()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["summary"])


if __name__ == "__main__":
    main()
