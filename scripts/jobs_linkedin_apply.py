#!/usr/bin/env python3
"""Postula en LinkedIn (Easy Apply): responde preguntas y registra CSV."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any
from jobs_common import load_config, pick_best_cv, vacancy_title
from jobs_linkedin_browser import ensure_login, launch_browser, new_context
from jobs_llm_answers import answer_field
from jobs_match import load_cv_index
from jobs_registry_csv import already_applied, append_application
from jobs_approval import require_approved, save_job


def _click_first(page, selectors: list[str]) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=5000)
                return True
        except Exception:
            continue
    for text in ("Solicitud sencilla", "Easy Apply", "Postular", "Apply"):
        try:
            btn = page.get_by_role("button", name=re.compile(text, re.I)).first
            if btn.count() and btn.is_visible():
                btn.click(timeout=5000)
                return True
        except Exception:
            continue
    return False


def _modal_root(page):
    for sel in (
        "div.jobs-easy-apply-modal",
        "div[data-test-modal]",
        "div.artdeco-modal",
        "div[role='dialog']",
    ):
        loc = page.locator(sel).first
        if loc.count() and loc.is_visible():
            return loc
    return page.locator("body")


def _collect_fields(modal) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for inp in modal.locator("input, textarea, select").all():
        try:
            if not inp.is_visible():
                continue
            tag = inp.evaluate("el => el.tagName.toLowerCase()")
            ftype = inp.get_attribute("type") or tag
            if ftype in {"hidden", "submit", "button", "file"}:
                continue
            label = inp.evaluate(
                """el => {
                const id = el.id;
                if (id) {
                  const lbl = document.querySelector(`label[for="${id}"]`);
                  if (lbl) return lbl.innerText;
                }
                return el.getAttribute('aria-label') || el.placeholder || el.name || '';
            }"""
            )
            options = []
            if tag == "select":
                options = inp.evaluate(
                    "el => Array.from(el.options).map(o => o.textContent.trim()).filter(Boolean)"
                )
            fields.append({"locator": inp, "label": str(label).strip(), "type": ftype, "options": options})
        except Exception:
            continue
    return fields


def _fill_fields(
    modal,
    *,
    profile: dict[str, Any],
    cv_excerpt: str,
    vacancy_text: str,
    answers_log: list[dict[str, str]],
) -> None:
    for field in _collect_fields(modal):
        label = field.get("label") or "field"
        loc = field["locator"]
        ftype = field.get("type") or "text"
        options = field.get("options") or []
        try:
            if ftype in {"checkbox", "radio"}:
                if not loc.is_checked():
                    loc.check(force=True)
                answers_log.append({"question": label, "answer": "checked"})
                continue
            if loc.input_value():
                continue
            if any(term in label.lower() for term in (
                "salary", "sueldo", "renta", "compensation", "visa",
                "autorización", "autorizacion", "authorization", "relocation",
            )):
                raise RuntimeError(f"Pregunta requiere aprobacion humana: {label}")
            ans = answer_field(
                label,
                field_type="select" if options else "text",
                options=options,
                profile=profile,
                cv_excerpt=cv_excerpt,
                vacancy_text=vacancy_text,
            )
            if options:
                try:
                    loc.select_option(label=ans)
                except Exception:
                    loc.select_option(value=ans)
            else:
                loc.fill(ans)
            answers_log.append({"question": label, "answer": ans})
        except Exception as exc:
            answers_log.append({"question": label, "answer": f"error:{exc}"})


def _upload_cv(modal, cv_path: str) -> bool:
    try:
        file_input = modal.locator("input[type='file']").first
        if file_input.count():
            file_input.set_input_files(cv_path)
            time.sleep(1.5)
            return True
    except Exception:
        pass
    return False


def _advance_modal(page, *, dry_run: bool = False) -> str:
    modal = _modal_root(page)
    for text in ("Enviar solicitud", "Submit application", "Submit", "Enviar", "Review", "Revisar", "Siguiente", "Next"):
        try:
            btn = modal.get_by_role("button", name=re.compile(f"^{re.escape(text)}$", re.I)).first
            if btn.count() and btn.is_visible() and not btn.is_disabled():
                if dry_run and text in ("Enviar solicitud", "Submit application", "Submit", "Enviar"):
                    return "review_only"
                btn.click(timeout=5000)
                time.sleep(1.2)
                return text.lower()
        except Exception:
            continue
    return ""


def apply_job_url(
    job_url: str,
    vacancy: dict[str, Any],
    cv: dict[str, Any],
    *,
    headless: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    cfg = load_config()
    if already_applied(job_url, cfg):
        return {
            "status": "skipped",
            "title": vacancy.get("title") or vacancy_title(vacancy.get("text", "")),
            "company": vacancy.get("company", ""),
            "job_url": job_url,
            "notes": "Ya postulado antes (CSV)",
        }

    profile = cfg
    cv_path = cv.get("path") or ""
    cv_excerpt = cv.get("excerpt") or ""
    vacancy_text = vacancy.get("text") or f"{vacancy.get('title')} {vacancy.get('company')}"
    answers_log: list[dict[str, str]] = []
    submitted = False
    error = ""

    with sync_playwright() as p:
        browser = launch_browser(p, headless=headless)
        context = new_context(browser, cfg)
        page = context.new_page()
        try:
            ensure_login(page, cfg)
            page.goto(job_url, wait_until="domcontentloaded", timeout=90000)
            time.sleep(3)
            if not _click_first(page, [
                "button.jobs-apply-button",
                "button.jobs-s-apply",
                "button[aria-label*='Easy Apply']",
                "button[aria-label*='Solicitud sencilla']",
            ]):
                raise RuntimeError("No encontre boton Easy Apply en la vacante.")

            for step in range(12):
                modal = _modal_root(page)
                _fill_fields(
                    modal,
                    profile=profile,
                    cv_excerpt=cv_excerpt,
                    vacancy_text=vacancy_text,
                    answers_log=answers_log,
                )
                if cv_path:
                    _upload_cv(modal, cv_path)
                if page.locator('iframe[src*="captcha"], [class*="captcha"]').count():
                    raise RuntimeError("CAPTCHA detectado; requiere intervencion humana.")
                action = _advance_modal(page, dry_run=dry_run)
                if action == "review_only":
                    break
                if "submit" in action or "enviar" in action:
                    submitted = True
                    time.sleep(2)
                    break
                if not action:
                    break
                time.sleep(1)
        except Exception as exc:
            error = str(exc)[:400]
        finally:
            context.close()
            browser.close()

    title = vacancy.get("title") or vacancy_title(vacancy_text)
    company = vacancy.get("company") or ""
    status = "applied" if submitted else ("dry_run" if dry_run and not error else "failed")
    notes = error or ("Preguntas respondidas: " + str(len(answers_log)))

    if not dry_run:
        append_application(
            title=title,
            company=company,
            job_url=job_url,
            status=status,
            cv_file=cv.get("filename", ""),
            match_score=vacancy.get("match_score", ""),
            questions_answered=answers_log,
            notes=notes,
            cfg=cfg,
        )

    return {
        "status": status,
        "title": title,
        "company": company,
        "job_url": job_url,
        "cv_file": cv.get("filename"),
        "questions_answered": answers_log,
        "notes": notes,
        "submitted": submitted,
    }


def resolve_job_url(vacancy: dict[str, Any]) -> str:
    for key in ("job_url", "url"):
        url = vacancy.get(key) or ""
        if "/jobs/view/" in url:
            return url.split("?")[0]
    raise ValueError("Vacante sin URL de LinkedIn Jobs. Corre: /jobs buscar linkedin")


def main() -> None:
    parser = argparse.ArgumentParser(description="Postular LinkedIn Easy Apply")
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--job-url", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from jobs_common import resolve_vacancy

    try:
        if args.job_url:
            vacancy = {"job_url": args.job_url, "url": args.job_url, "text": args.job_url}
        else:
            vacancy = resolve_vacancy("", args.index if args.index else None)
        job_url = resolve_job_url(vacancy)
        job_id_match = re.search(r"/jobs/view/(\d+)", job_url)
        if not job_id_match:
            raise ValueError("No pude resolver job_id LinkedIn.")
        approved_job = require_approved(job_id_match.group(1))
        vacancy = {**vacancy, **approved_job, "text": approved_job.get("description", "")}
        cv_index = load_cv_index()
        if not cv_index:
            raise RuntimeError("Indexa CVs primero: jobs_cv_index.py --json")
        cv = pick_best_cv(vacancy.get("text", ""), cv_index) or cv_index[0]
        generated = approved_job.get("generated_cv") or ""
        if generated and Path(generated).exists():
            cv = {"filename": Path(generated).name, "path": generated, "excerpt": vacancy.get("text", "")[:1500]}
        result = apply_job_url(
            job_url,
            vacancy,
            cv,
            headless=not args.headed,
            dry_run=args.dry_run,
        )
        if result["status"] == "applied":
            approved_job["decision_status"] = "applied"
            approved_job["applied_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            save_job(approved_job)
        icon = "✅" if result["status"] == "applied" else "⚠️"
        payload = {
            "status": "ok" if result["status"] in {"applied", "dry_run", "skipped"} else "error",
            "agent": "jobs",
            "result": result,
            "whatsapp_reply": (
                f"{icon} *Jobs — postulacion {result['status']}*\n"
                f"*{result.get('title')}* @ {result.get('company')}\n"
                f"🔗 {result.get('job_url')}\n"
                f"CV: `{result.get('cv_file')}`\n"
                f"Preguntas: {len(result.get('questions_answered') or [])}\n"
                f"{result.get('notes', '')}"
            ),
        }
    except Exception as exc:
        payload = {"status": "error", "agent": "jobs", "whatsapp_reply": f"Jobs postular: {exc}"}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload.get("whatsapp_reply", ""))


if __name__ == "__main__":
    main()
