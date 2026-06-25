#!/usr/bin/env python3
"""Login Computrabajo candidato (guarda sesion para Jobs)."""

from __future__ import annotations

import argparse
import time

from jobs_computrabajo_browser import (
    HOME_URL,
    ensure_login,
    is_logged_in,
    load_computrabajo_credentials,
    new_context,
    save_session_if_logged_in,
    storage_state_path,
    submit_login_form,
)
from jobs_linkedin_browser import launch_browser


def wait_manual_login(page, wait_sec: int = 600) -> None:
    credentials = load_computrabajo_credentials()
    print("=== LOGIN Computrabajo ===")
    print("1. Completa email/contraseña en Chromium si hace falta")
    print("2. Debes quedar en el area candidato (home / mis postulaciones)")
    print(f"3. Sesion se guardara en: {storage_state_path()}")
    if credentials:
        email, password = credentials
        try:
            submit_login_form(page, email, password)
            path = save_session_if_logged_in(page)
            if path:
                print(f"Sesion guardada (login automatico OK): {path}")
                return
        except Exception as exc:
            print(f"Auto-login fallo ({exc}); continua manual en el browser.")
    print("Si aun no entraste, completa el login en el browser y presiona ENTER aqui.")
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        try:
            input()
            break
        except EOFError:
            time.sleep(3)
    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    path = save_session_if_logged_in(page)
    if not path:
        raise RuntimeError("Login no completado: no se guardo sesion Computrabajo.")
    print(f"Sesion guardada: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Login Computrabajo candidato")
    parser.add_argument("action", nargs="?", default="login", choices=["login", "auto", "check"])
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    from jobs_computrabajo_browser import computrabajo_portal_cfg

    headed = args.headed and not args.headless
    with sync_playwright() as p:
        browser = launch_browser(p, headless=not headed)
        context = new_context(browser)
        page = context.new_page()
        try:
            if args.action == "check":
                portal = computrabajo_portal_cfg()
                page.goto(portal["home_url"], wait_until="domcontentloaded", timeout=90000)
                time.sleep(2)
                ok = is_logged_in(page)
                path = storage_state_path()
                print(f"sesion_valida={ok} archivo={path} existe={path.exists()}")
                if not ok:
                    raise SystemExit(1)
                return
            if args.action == "auto":
                path = ensure_login(page)
                if not path:
                    raise RuntimeError("Login OK pero no se pudo persistir sesion Computrabajo.")
                print(f"Sesion guardada: {path}")
            else:
                wait_manual_login(page)
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
