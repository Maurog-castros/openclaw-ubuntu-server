#!/usr/bin/env python3
"""Login manual ChileTrabajos (guarda sesion para scraping Jobs)."""

from __future__ import annotations

import argparse
import time

from jobs_chiletrabajos_browser import (
    HOME_URL,
    LOGIN_URL,
    ensure_login,
    is_logged_in,
    load_chiletrabajos_credentials,
    new_context,
    save_session_if_logged_in,
    storage_state_path,
)
from jobs_linkedin_browser import launch_browser


def try_auto_submit(page) -> bool:
    credentials = load_chiletrabajos_credentials()
    if not credentials:
        return False
    email, password = credentials
    try:
        page.fill("#username, input[name='username']", email)
        page.fill("#password, input[name='password']", password)
        page.click("input[name='login'], input[type='submit'][name='login']")
        page.wait_for_load_state("domcontentloaded", timeout=90000)
        time.sleep(2)
    except Exception:
        return False
    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    return is_logged_in(page)


def wait_manual_login(page, wait_sec: int = 600) -> None:
    print("LOGIN ChileTrabajos — completa email/contraseña en Chromium si hace falta.")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
    if try_auto_submit(page):
        path = save_session_if_logged_in(page)
        if path:
            print(f"Sesion guardada (login OK): {path}")
            return
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
        raise RuntimeError("Login no completado: no se guardo sesion.")
    print(f"Sesion guardada: {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["login", "auto"])
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch_browser(p, headless=not args.headed)
        context = new_context(browser)
        page = context.new_page()
        try:
            if args.action == "auto":
                path = ensure_login(page)
                if not path:
                    raise RuntimeError("Login OK pero no se pudo persistir sesion.")
                print(f"Sesion guardada: {path}")
            else:
                wait_manual_login(page)
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
