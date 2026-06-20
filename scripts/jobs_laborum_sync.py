#!/usr/bin/env python3
"""Sincroniza experiencia Laborum desde perfil extraído del CV."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from jobs_common import JOBS_WS
from jobs_laborum_profile import build_profile
from runtime_paths import secret_file

LABORUM_URL = "https://www.laborum.cl/candidatos/curriculum/experiencia/agregar"
STATE_PATH = secret_file("runtime/secrets/laborum_storage_state.json")
OUTPUT_DIR = JOBS_WS / "laborum"
SYNC_STATE = OUTPUT_DIR / "sync_state.json"
MONTH_NAMES = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}


def load_registry() -> dict[str, Any]:
    try:
        return json.loads(SYNC_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"synced": {}}


def save_registry(registry: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    temporary = SYNC_STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(SYNC_STATE)


def launch(playwright: Any, *, headless: bool) -> Any:
    chrome = "/opt/google/chrome/chrome"
    kwargs = {
        "headless": headless,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if Path(chrome).exists():
        kwargs["executable_path"] = chrome
    return playwright.chromium.launch(**kwargs)


def context(browser: Any) -> Any:
    if not STATE_PATH.exists():
        raise FileNotFoundError("Falta sesión Laborum. Ejecuta jobs_laborum_login.py --headed.")
    return browser.new_context(
        storage_state=str(STATE_PATH),
        viewport={"width": 1440, "height": 1000},
        locale="es-CL",
    )


def select_react(dialog: Any, page: Any, select_id: int, query: str, exact: str) -> None:
    input_box = dialog.locator(f"#react-select-{select_id}-input")
    if input_box.get_attribute("readonly") is not None:
        input_box.locator("xpath=../..").click(force=True)
    else:
        input_box.fill(query)
    option = page.get_by_text(exact, exact=True).last
    option.wait_for(state="visible", timeout=10000)
    option.click()
    time.sleep(0.2)


def fill_experience(page: Any, experience: dict[str, Any]) -> None:
    dialog = page.get_by_role("dialog", name="Sumar experiencia laboral *")
    dialog.locator("#empresa").fill(experience["company"])
    select_react(dialog, page, 5, "Informática", experience["company_activity"])
    dialog.locator("#puesto").fill(experience["role"])
    select_react(dialog, page, 6, "Senior", experience["experience_level"])
    select_react(dialog, page, 7, "Tecnología", experience["area"])
    select_react(dialog, page, 8, experience["subarea"], experience["subarea"])
    select_react(dialog, page, 9, "Chile", experience["country"])
    select_react(dialog, page, 10, MONTH_NAMES[experience["start_month"]], MONTH_NAMES[experience["start_month"]])
    select_react(dialog, page, 11, str(experience["start_year"]), str(experience["start_year"]))
    if experience["current"]:
        dialog.locator("#alPresente").check()
    else:
        select_react(dialog, page, 12, MONTH_NAMES[experience["end_month"]], MONTH_NAMES[experience["end_month"]])
        select_react(dialog, page, 13, str(experience["end_year"]), str(experience["end_year"]))
    dialog.locator("#detalle").fill(experience["description"])
    dialog.locator("#personasACargo").fill(str(experience["people_managed"]))
    budget_id = "#radiobutton-presupuesto-true" if experience["managed_budget"] else "#radiobutton-presupuesto-false"
    dialog.locator(budget_id).check(force=True)


def assert_laborum_ready(page: Any) -> None:
    if "Attention Required" in page.title() or "cloudflare" in page.url.lower():
        raise RuntimeError("Cloudflare bloqueó Laborum. Ejecuta headed en DISPLAY XRDP.")
    page.get_by_role("dialog", name="Sumar experiencia laboral *").wait_for(timeout=20000)


def sync(*, cv_path: Path | None, apply: bool, headless: bool) -> dict[str, Any]:
    profile = build_profile(cv_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    registry = load_registry()
    synced = registry.setdefault("synced", {})
    results: list[dict[str, str]] = []
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = launch(playwright, headless=headless)
        browser_context = context(browser)
        page = browser_context.new_page()
        try:
            experiences = profile["experiences"] if apply else profile["experiences"][:1]
            for experience in experiences:
                if experience["key"] in synced:
                    results.append({"key": experience["key"], "status": "skipped", "company": experience["company"]})
                    continue
                page.goto(LABORUM_URL, wait_until="domcontentloaded", timeout=90000)
                time.sleep(4)
                assert_laborum_ready(page)
                body = page.locator("body").inner_text()
                if experience["company"] in body and experience["role"] in body:
                    synced[experience["key"]] = {"status": "already_present"}
                    save_registry(registry)
                    results.append({"key": experience["key"], "status": "already_present", "company": experience["company"]})
                    continue
                fill_experience(page, experience)
                save = page.locator("#experiencias-form-guardar:visible").first
                save.wait_for(state="visible", timeout=10000)
                if save.is_disabled():
                    raise RuntimeError(f"Formulario inválido para {experience['company']}; Guardar deshabilitado.")
                if not apply:
                    preview = OUTPUT_DIR / "preview.png"
                    page.screenshot(path=str(preview), full_page=True)
                    results.append({"key": experience["key"], "status": "preview", "company": experience["company"]})
                    break
                save.click()
                page.get_by_role("dialog", name="Sumar experiencia laboral *").wait_for(state="hidden", timeout=30000)
                time.sleep(1)
                if experience["company"] not in page.locator("body").inner_text():
                    raise RuntimeError(f"Laborum no confirmó experiencia {experience['company']}.")
                synced[experience["key"]] = {
                    "status": "saved",
                    "company": experience["company"],
                    "role": experience["role"],
                    "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                }
                save_registry(registry)
                results.append({"key": experience["key"], "status": "saved", "company": experience["company"]})
        except Exception:
            error_shot = OUTPUT_DIR / "sync-error.png"
            page.screenshot(path=str(error_shot), full_page=True)
            raise
        finally:
            browser_context.close()
            browser.close()
    return {"profile": profile, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sincronizar CV con Laborum")
    parser.add_argument("--cv", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.apply and args.confirm != "UPDATE-LABORUM":
            raise PermissionError("Apply requiere --confirm UPDATE-LABORUM")
        result = sync(
            cv_path=Path(args.cv) if args.cv else None,
            apply=args.apply,
            headless=args.headless,
        )
        counts: dict[str, int] = {}
        for row in result["results"]:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        payload = {
            "status": "ok",
            "agent": "jobs",
            "mode": "apply" if args.apply else "preview",
            "counts": counts,
            "results": result["results"],
            "profile_file": str(OUTPUT_DIR / "profile.json"),
            "preview_file": str(OUTPUT_DIR / "preview.png") if not args.apply else "",
            "whatsapp_reply": (
                f"Laborum {'actualizado' if args.apply else 'preview listo'}: {counts}. "
                f"Perfil: {OUTPUT_DIR / 'profile.json'}"
            ),
        }
    except Exception as exc:
        payload = {
            "status": "error",
            "agent": "jobs",
            "whatsapp_reply": f"Laborum sync: {exc}",
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["whatsapp_reply"])


if __name__ == "__main__":
    main()
