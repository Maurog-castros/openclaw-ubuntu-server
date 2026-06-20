#!/usr/bin/env python3
"""Login manual Laborum — sin auto-submit (no dispara emails MFA)."""

from __future__ import annotations

import argparse
import time

from jobs_laborum_browser import (
    is_logged_in,
    laborum_cfg,
    launch_laborum_browser,
    new_context,
    save_session_if_logged_in,
    storage_state_path,
)


def wait_manual_login(page, cfg, wait_sec: int = 900) -> None:
    lb = laborum_cfg(cfg)
    state = storage_state_path(cfg)
    print("=== LOGIN MANUAL Laborum ===")
    print("1. En Chromium: email, contraseña y codigo MFA del correo")
    print("2. Debes quedar en curriculum / postulaciones (sesion activa)")
    print("3. Vuelve aca y presiona ENTER para guardar sesion")
    print(f"   Sesion se guardara en: {state}")
    page.goto(lb["login_url"], wait_until="domcontentloaded", timeout=90000)
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        if is_logged_in(page):
            path = save_session_if_logged_in(page, cfg)
            if path:
                print(f"Sesion guardada (detectada en browser): {path}")
                return
        try:
            input("ENTER cuando hayas terminado el login en Chromium... ")
            break
        except EOFError:
            time.sleep(5)
    page.goto(lb["curriculum_url"], wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    path = save_session_if_logged_in(page, cfg)
    if not path:
        raise RuntimeError(
            "Login no completado. Asegurate de ingresar el codigo MFA y ver tu curriculum en Laborum."
        )
    print(f"Sesion guardada: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Login manual Laborum (no envia emails extra)")
    parser.add_argument(
        "action",
        nargs="?",
        default="login",
        choices=["login", "check"],
        help="login=browser manual; check=solo verifica sesion guardada",
    )
    parser.add_argument("--headed", action="store_true", default=True)
    parser.add_argument("--headless", action="store_true", help="Sin ventana (solo check util)")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    from jobs_common import load_config

    cfg = load_config()
    headed = args.headed and not args.headless
    with sync_playwright() as p:
        browser = launch_laborum_browser(p, headless=not headed)
        context = new_context(browser, cfg)
        page = context.new_page()
        try:
            if args.action == "check":
                lb = laborum_cfg(cfg)
                page.goto(lb["curriculum_url"], wait_until="domcontentloaded", timeout=90000)
                time.sleep(2)
                ok = is_logged_in(page)
                path = storage_state_path(cfg)
                print(f"sesion_valida={ok} archivo={path} existe={path.exists()}")
                if not ok:
                    raise SystemExit(1)
                return
            wait_manual_login(page, cfg)
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
