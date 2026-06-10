#!/usr/bin/env python3
"""Remedia hallazgos conocidos del agente soporte."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from support_common import (
    AUTO_FIX_CATEGORIES,
    FIN_RESET_CLOSE_CATEGORIES,
    REPO_ROOT,
    clear_whatsapp_pending_and_reset_sessions,
    gateway_healthy,
    git_commit_push,
    live_health,
    load_findings,
    mark_category_findings_remediated,
    now_iso,
    reopen_failed_findings,
    bootstrap_budget_ok,
    remediate_bootstrap_budget,
    run_cmd,
    update_finding,
    wait_gateway_healthy,
    whatsapp_pending_count,
)


def remediate_clear_whatsapp_and_reset() -> str:
    result = clear_whatsapp_pending_and_reset_sessions(restart_gateway=True)
    return (
        f"pending deleted: {result.get('pending_deleted', 0)}; "
        f"failed fin: {result.get('failed_deleted', 0)}; "
        f"sessions: {','.join(result.get('sessions_removed') or []) or 'ninguna'}; "
        f"{result.get('restart', '')}"
    )[:800]


def remediate_restart_gateway() -> str:
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
    msg = (out or err or f"exit={code}")[:400]
    if wait_gateway_healthy():
        msg += " | gateway healthy tras espera"
    return msg


def pick_fixable_findings(categories: List[str] | None = None) -> List[dict]:
    rows = load_findings()
    out = []
    for row in rows:
        if row.get("status") not in {"open", "failed"}:
            continue
        cat = row.get("category") or ""
        if categories and cat not in categories:
            continue
        if cat in AUTO_FIX_CATEGORIES:
            out.append(row)
    return out


def remediation_verified(*, wait: bool = True) -> bool:
    if wait and not gateway_healthy():
        wait_gateway_healthy()
    health = live_health()
    return (
        health.get("gateway_healthy")
        and int(health.get("whatsapp_pending") or 0) == 0
        and not health.get("fin_session_running")
        and int(health.get("fin_failed_deliveries") or 0) == 0
        and health.get("fin_session_heavy") is None
    )


def remediate_finding(finding_id: str, *, do_commit: bool) -> dict:
    rows = load_findings()
    row = next((r for r in rows if r.get("finding_id") == finding_id), None)
    if not row:
        return {"status": "not_found", "finding_id": finding_id}
    return _apply_fix(row, do_commit=do_commit)


def _apply_fix(row: dict, *, do_commit: bool) -> dict:
    cat = row.get("category") or ""
    actions: List[str] = []

    if cat in {"session_stuck", "context_overflow", "session_heavy", "whatsapp_pending"}:
        actions.append(remediate_clear_whatsapp_and_reset())
    elif cat == "gateway_unhealthy":
        actions.append(remediate_restart_gateway())
        wait_gateway_healthy()
    elif cat == "bootstrap_budget":
        actions.append(remediate_bootstrap_budget())
    else:
        return {
            "status": "skip",
            "finding_id": row.get("finding_id"),
            "message": f"Sin playbook auto para {cat}",
        }

    verified = bootstrap_budget_ok() if cat == "bootstrap_budget" else remediation_verified()
    commit_info = {}
    action_text = " | ".join(actions)[:500]
    if do_commit and verified:
        commit_info = git_commit_push(f"fix(supp): {row.get('summary', cat)[:60]}")

    close_cats = (
        FIN_RESET_CLOSE_CATEGORIES
        if cat in {"session_stuck", "context_overflow", "session_heavy", "whatsapp_pending"}
        else frozenset({cat})
    )
    if verified:
        mark_category_findings_remediated(
            close_cats,
            action=action_text,
            commit_hash=(commit_info.get("commit") or "")[:64],
        )
    else:
        update_finding(
            row["finding_id"],
            {
                "status": "failed",
                "remediated_at": now_iso(),
                "remediation_action": action_text,
                "verified_at": "",
                "commit_hash": "",
            },
        )

    health = live_health()
    summary = (
        f"Fix {row.get('category')}: {'OK' if verified else 'parcial'}\n"
        f"Gateway: {'healthy' if health.get('gateway_healthy') else 'revisar'}\n"
        f"Pending WA: {health.get('whatsapp_pending', 0)}\n"
        f"Sesion fin: {health.get('fin_session', {}).get('status', '?')}\n"
        f"Entregas failed fin: {health.get('fin_failed_deliveries', 0)}\n"
        f"Commit: {commit_info.get('commit', 'ninguno')}"
    )
    return {
        "status": "ok" if verified else "partial",
        "finding_id": row.get("finding_id"),
        "verified": verified,
        "commit": commit_info,
        "summary": summary,
        "whatsapp_reply": summary,
    }


def remediate_live(*, do_commit: bool) -> dict:
    """Ejecuta playbook aunque el CSV no tenga filas open (estado vivo)."""
    health = live_health()
    if not health.get("needs_remediation"):
        return {"status": "skip", "verified": True, "message": "Sistema fin OK en vivo."}

    actions: List[str] = []
    if not health.get("gateway_healthy"):
        actions.append(remediate_restart_gateway())
        wait_gateway_healthy()
    if (
        health.get("fin_session_running")
        or health.get("fin_session_heavy")
        or int(health.get("whatsapp_pending") or 0) > 0
        or int(health.get("fin_failed_deliveries") or 0) > 0
    ):
        actions.append(remediate_clear_whatsapp_and_reset())
    if load_findings_open_bootstrap():
        actions.append(remediate_bootstrap_budget())

    verified = remediation_verified() and bootstrap_budget_ok()
    action_text = " | ".join(actions)[:500]
    commit_info = {}
    if do_commit and verified:
        commit_info = git_commit_push("fix(supp): auto-fix estado vivo fin")
    if verified:
        mark_category_findings_remediated(
            FIN_RESET_CLOSE_CATEGORIES | frozenset({"bootstrap_budget"}),
            action=action_text,
            commit_hash=(commit_info.get("commit") or "")[:64],
        )
    health = live_health()
    summary = (
        "Auto-fix (estado vivo):\n"
        f"Gateway: {'healthy' if health.get('gateway_healthy') else 'revisar'}\n"
        f"Pending WA: {health.get('whatsapp_pending', 0)}\n"
        f"Sesion fin: {health.get('fin_session', {}).get('status', '?')}\n"
        f"Entregas failed fin: {health.get('fin_failed_deliveries', 0)}\n"
        f"Resultado: {'OK' if verified else 'parcial — reintenta o revisa logs'}"
    )
    return {
        "status": "ok" if verified else "partial",
        "verified": verified,
        "actions": actions,
        "summary": summary,
        "whatsapp_reply": summary,
    }


def load_findings_open_bootstrap() -> bool:
    return any(
        r.get("category") == "bootstrap_budget" and r.get("status") in {"open", "failed"}
        for r in load_findings()
    )


def remediate_auto(*, do_commit: bool) -> dict:
    reopen_failed_findings()
    health = live_health()
    if health.get("needs_remediation"):
        return remediate_live(do_commit=do_commit)

    targets = pick_fixable_findings()
    if not targets:
        msg = "Sistema fin OK. Sin hallazgos pendientes en CSV."
        return {"status": "ok", "fixed": 0, "summary": msg, "whatsapp_reply": msg}

    results = [_apply_fix(row, do_commit=do_commit) for row in targets[:3]]
    fixed = sum(1 for r in results if r.get("verified"))
    summary = f"Remediados: {fixed}/{len(results)}\n" + "\n".join(
        r.get("summary", "")[:120] for r in results
    )
    return {
        "status": "ok",
        "fixed": fixed,
        "results": results,
        "summary": summary,
        "whatsapp_reply": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Remedia hallazgos /supp")
    parser.add_argument("--finding-id", default="")
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--no-commit", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.finding_id:
        result = remediate_finding(args.finding_id, do_commit=not args.no_commit)
    elif args.auto:
        result = remediate_auto(do_commit=not args.no_commit)
    else:
        result = {"status": "error", "message": "Usa --auto o --finding-id"}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("whatsapp_reply") or result.get("summary") or result.get("message"))


if __name__ == "__main__":
    main()
