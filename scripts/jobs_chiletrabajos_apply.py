#!/usr/bin/env python3
"""Postula en ChileTrabajos (requiere sesion activa)."""

from __future__ import annotations

import argparse
import json
import re
import time
from typing import Any

from jobs_approval import require_approved, save_job
from jobs_chiletrabajos_browser import chiletrabajos_session, ensure_login, is_logged_in, save_session_if_logged_in
from jobs_common import load_config
from jobs_linkedin_browser import launch_browser, new_context
from jobs_registry_csv import append_application, already_applied


def postular_url(job_id: str) -> str:
    return f"https://www.chiletrabajos.cl/trabajo/postular/{job_id}"


def _click_postular(page) -> bool:
    selectors = [
        "input[type=submit][value*='Postular']",
        "button[type=submit]",
        "input.btn-primary[type=submit]",
        "button.btn-primary",
        "a.btn-primary[href*='postular']",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=8000)
                return True
        except Exception:
            continue
    for text in ("Postular", "Enviar postulación", "Enviar", "Confirmar"):
        try:
            btn = page.get_by_role("button", name=re.compile(text, re.I)).first
            if btn.count() and btn.is_visible():
                btn.click(timeout=8000)
                return True
        except Exception:
            continue
    return False


def _success(body: str) -> bool:
    blob = body.lower()
    markers = (
        "postulación enviada",
        "postulacion enviada",
        "postulaste",
        "ya postulaste",
        "postulación realizada",
        "postulacion realizada",
        "gracias por postular",
        "tu postulación",
    )
    return any(m in blob for m in markers)


def apply_job_id(job_id: str, *, dry_run: bool = False, headed: bool = False) -> dict[str, Any]:
    approved = require_approved(job_id)
    job_url = str(approved.get("job_url") or "")
    if "chiletrabajos.cl" not in job_url:
        raise ValueError(f"Vacante {job_id} no es de ChileTrabajos.")

    cfg = load_config()
    if already_applied(job_url, cfg):
        return {
            "status": "skipped",
            "job_id": job_id,
            "job_url": job_url,
            "notes": "Ya registrada en applications.csv",
        }

    submitted = False
    error = ""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = launch_browser(playwright, headless=not headed)
        context = new_context(browser, cfg)
        page = context.new_page()
        try:
            ensure_login(page, cfg)
            if not is_logged_in(page):
                raise RuntimeError("Sesion ChileTrabajos invalida. Corre: /jobs chiletrabajos login")
            page.goto(postular_url(job_id), wait_until="domcontentloaded", timeout=90000)
            time.sleep(2)
            body = page.inner_text("body")
            if _success(body) or "ya postul" in body.lower():
                submitted = True
            elif dry_run:
                submitted = False
            else:
                if not _click_postular(page):
                    raise RuntimeError("No encontre boton Postular en ChileTrabajos.")
                page.wait_for_load_state("domcontentloaded", timeout=90000)
                time.sleep(2)
                body = page.inner_text("body")
                submitted = _success(body) or "ya postul" in body.lower()
                if not submitted:
                    raise RuntimeError("Postulacion no confirmada en pagina ChileTrabajos.")
            save_session_if_logged_in(page, cfg)
        except Exception as exc:
            error = str(exc)[:400]
        finally:
            context.close()
            browser.close()

    title = str(approved.get("title") or "")
    company = str(approved.get("company") or "")
    cv_file = str((approved.get("best_cv") or {}).get("file") or "")
    status = "applied" if submitted else ("dry_run" if dry_run and not error else "failed")
    notes = error or ("Postulacion ChileTrabajos OK" if submitted else "dry_run")

    if not dry_run and submitted:
        append_application(
            title=title,
            company=company,
            job_url=job_url,
            status=status,
            cv_file=cv_file,
            match_score=approved.get("vacancy_score", ""),
            notes=notes,
            source="chiletrabajos",
            cfg=cfg,
        )
        approved["decision_status"] = "applied"
        approved["applied_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        save_job(approved)

    return {
        "status": status,
        "job_id": job_id,
        "title": title,
        "company": company,
        "job_url": job_url,
        "cv_file": cv_file,
        "notes": notes,
        "submitted": submitted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Postular ChileTrabajos")
    parser.add_argument("job_id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = apply_job_id(args.job_id, dry_run=args.dry_run, headed=args.headed)
        icon = "✅" if result["status"] == "applied" else "⚠️"
        payload = {
            "status": "ok" if result["status"] in {"applied", "dry_run", "skipped"} else "error",
            "agent": "jobs",
            "result": result,
            "whatsapp_reply": (
                f"{icon} *Jobs — ChileTrabajos {result['status']}*\n"
                f"*{result.get('title')}* @ {result.get('company')}\n"
                f"🔗 {result.get('job_url')}\n"
                f"{result.get('notes', '')}"
            ),
        }
    except Exception as exc:
        payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Jobs postular ChileTrabajos: {exc}"}

    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))


if __name__ == "__main__":
    main()
