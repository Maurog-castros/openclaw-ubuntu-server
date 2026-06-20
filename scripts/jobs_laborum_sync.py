#!/usr/bin/env python3
"""Sincroniza experiencia laboral de Mauro en Laborum.cl."""

from __future__ import annotations

import argparse
import json
import re
import time
from typing import Any

from jobs_common import load_config
from jobs_laborum_browser import ensure_login, launch_laborum_browser, new_context, save_session_if_logged_in
from jobs_profile_experience import best_cv_path, load_experiences


def _month_year(value: str) -> tuple[str, str]:
    value = (value or "").strip()
    if not value:
        return "", ""
    match = re.match(r"(\d{4})-(\d{2})", value)
    if match:
        year, month = match.group(1), match.group(2)
        months = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        idx = int(month)
        return months[idx] if 1 <= idx <= 12 else month, year
    return value, ""


def _fill_if_present(page, labels: list[str], value: str) -> bool:
    if not value:
        return False
    for label in labels:
        try:
            loc = page.get_by_label(label, exact=False)
            if loc.count():
                loc.first.fill(value)
                return True
        except Exception:
            pass
    return False


def _select_react_option(page, label: str, value: str) -> bool:
    if not value:
        return False
    try:
        field = page.get_by_label(label, exact=False).first
        field.click(timeout=3000)
        time.sleep(0.4)
        page.keyboard.type(value[:40])
        time.sleep(0.8)
        option = page.get_by_role("option", name=re.compile(re.escape(value[:20]), re.I))
        if option.count():
            option.first.click(timeout=3000)
            return True
        page.keyboard.press("Enter")
        return True
    except Exception:
        return False


def fill_experience_form(page, exp: dict[str, Any]) -> None:
    cfg = load_config()
    url = ((cfg.get("job_portals") or {}).get("laborum") or {}).get(
        "experience_url", "https://www.laborum.cl/candidatos/curriculum/experiencia/agregar"
    )
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    _fill_if_present(page, ["Puesto", "Cargo", "Nombre del puesto"], str(exp.get("title") or ""))
    _fill_if_present(page, ["Empresa", "Compañía", "Compania"], str(exp.get("company") or ""))
    _fill_if_present(page, ["Descripción", "Descripcion", "Funciones"], str(exp.get("description") or ""))
    start_m, start_y = _month_year(str(exp.get("start") or ""))
    end_m, end_y = _month_year(str(exp.get("end") or ""))
    _select_react_option(page, "Mes", start_m)
    _select_react_option(page, "Año", start_y)
    if exp.get("current"):
        try:
            page.get_by_label("Trabajo actual", exact=False).check(timeout=2000)
        except Exception:
            try:
                page.get_by_text("Actualmente trabajo aquí", exact=False).click(timeout=2000)
            except Exception:
                pass
    elif end_m and end_y:
        _select_react_option(page, "Mes", end_m)
        _select_react_option(page, "Año", end_y)
    saved = False
    for label in ("Guardar", "Agregar", "Continuar", "Siguiente"):
        try:
            btn = page.get_by_role("button", name=re.compile(label, re.I))
            if btn.count():
                btn.first.click(timeout=5000)
                saved = True
                break
        except Exception:
            continue
    if not saved:
        raise RuntimeError(f"No pude guardar experiencia {exp.get('id')} en Laborum (revisar selectores/formulario).")
    time.sleep(2)


def upload_cv_pdf(page, cv_path) -> None:
    page.goto("https://www.laborum.cl/candidatos/curriculum", wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    selectors = [
        "input[type='file']",
        "input[accept*='pdf']",
        "input[name*='cv']",
    ]
    for sel in selectors:
        try:
            input_el = page.locator(sel).first
            if input_el.count():
                input_el.set_input_files(str(cv_path))
                time.sleep(4)
                return
        except Exception:
            continue
    raise RuntimeError("No encontre input de subida de CV en Laborum (Mia/importar PDF).")


def sync_experiences(*, headless: bool = True, dry_run: bool = False, mode: str = "form") -> dict[str, Any]:
    experiences = load_experiences()
    if not experiences:
        raise RuntimeError("Sin experiencias en config/jobs/profile_experience.json")
    if dry_run:
        results = [
            {"id": exp.get("id", ""), "company": exp.get("company", ""), "title": exp.get("title", ""), "status": "dry_run"}
            for exp in experiences
        ]
        if mode == "cv":
            results = [{"action": "cv_upload", "file": str(best_cv_path()), "status": "dry_run"}]
        return {"status": "ok", "mode": mode, "count": len(results), "results": results}
    cfg = load_config()
    results: list[dict[str, str]] = []
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch_laborum_browser(p, headless=headless)
        context = new_context(browser, cfg)
        page = context.new_page()
        try:
            ensure_login(page, cfg)
            if mode == "cv":
                cv = best_cv_path(cfg)
                if dry_run:
                    results.append({"action": "cv_upload", "file": str(cv), "status": "dry_run"})
                else:
                    upload_cv_pdf(page, cv)
                    results.append({"action": "cv_upload", "file": str(cv), "status": "ok"})
            else:
                for exp in experiences:
                    if dry_run:
                        results.append({"id": exp.get("id", ""), "company": exp.get("company", ""), "status": "dry_run"})
                        continue
                    fill_experience_form(page, exp)
                    results.append({"id": exp.get("id", ""), "company": exp.get("company", ""), "status": "ok"})
            save_session_if_logged_in(page, cfg)
        finally:
            context.close()
            browser.close()
    return {"status": "ok", "mode": mode, "count": len(results), "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync experiencia Laborum")
    parser.add_argument("--mode", choices=["form", "cv"], default="form", help="form=campo a campo; cv=subir PDF (Mia)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        payload = {
            "status": "ok",
            "agent": "jobs",
            "portal": "laborum",
            **sync_experiences(headless=not args.headed, dry_run=args.dry_run, mode=args.mode),
            "whatsapp_reply": "",
        }
        if args.mode == "cv":
            payload["whatsapp_reply"] = f"Laborum: CV subido ({payload['count']} acciones)."
        else:
            payload["whatsapp_reply"] = f"Laborum: {payload['count']} experiencias sincronizadas."
        if args.dry_run:
            payload["whatsapp_reply"] = "Laborum dry-run: " + payload["whatsapp_reply"]
    except Exception as exc:
        payload = {
            "status": "error",
            "agent": "jobs",
            "portal": "laborum",
            "whatsapp_reply": f"Laborum sync fallo: {exc}",
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("whatsapp_reply", ""))
    if payload.get("status") != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
