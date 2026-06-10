#!/usr/bin/env python3
"""Login manual LinkedIn personal (postulaciones Jobs)."""

from __future__ import annotations

import argparse
import time

from jobs_linkedin_browser import launch_browser, new_context, storage_state_path


def wait_manual_login(page, storage_state, wait_sec: int = 600) -> None:
    print("LOGIN LinkedIn personal — completa en Chromium y presiona ENTER aqui.")
    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=90000)
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        try:
            input()
            break
        except EOFError:
            time.sleep(3)
    storage_state.parent.mkdir(parents=True, exist_ok=True)
    page.context.storage_state(path=str(storage_state))
    print(f"Sesion guardada: {storage_state}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["login"])
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    state = storage_state_path()
    with sync_playwright() as p:
        browser = launch_browser(p, headless=not args.headed)
        context = new_context(browser)
        page = context.new_page()
        try:
            wait_manual_login(page, state)
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
