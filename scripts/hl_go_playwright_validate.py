#!/usr/bin/env python3
"""Smoke QA HL-Go con Playwright: login y landing."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from hl_go_common import app_root, app_url, load_dotenv, parse_port_from_url, port_open

ROOT = Path(__file__).resolve().parent.parent
PLAYWRIGHT_PY = ROOT / ".venv-linkedin-intel/bin/python"
if not PLAYWRIGHT_PY.exists():
    PLAYWRIGHT_PY = Path(sys.executable)


def start_server() -> subprocess.Popen[str] | None:
    app = app_root()
    start_sh = app / "start.sh"
    if not start_sh.exists():
        return None
    cfg = load_dotenv()
    url = app_url(cfg)
    port = parse_port_from_url(url)
    if port_open("127.0.0.1", port):
        return None
    proc = subprocess.Popen(
        ["bash", str(start_sh)],
        cwd=str(app),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    for _ in range(30):
        if port_open("127.0.0.1", port):
            return proc
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f"Servidor PHP no levanto en puerto {port}")


def launch_browser(playwright: Any, *, headless: bool) -> Any:
    chrome_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]
    args = ["--disable-blink-features=AutomationControlled"]
    for chrome in chrome_paths:
        if Path(chrome).exists():
            return playwright.chromium.launch(headless=headless, executable_path=chrome, args=args)
    try:
        return playwright.chromium.launch(headless=headless, channel="chrome", args=args)
    except Exception:
        return playwright.chromium.launch(headless=headless, args=args)


def run_checks(*, headed: bool) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    cfg = load_dotenv()
    base = app_url(cfg)
    user = cfg.get("HL_TEST_USER") or "mauro"
    password = cfg.get("HL_TEST_PASS") or "mauro1234"
    checks: list[dict[str, Any]] = []
    server = start_server()

    try:
        with sync_playwright() as p:
            browser = launch_browser(p, headless=not headed)
            page = browser.new_page(viewport={"width": 1400, "height": 900})

            page.goto(base + "/", wait_until="networkidle", timeout=30000)
            login_form = page.locator("#login-form")
            login_form.wait_for(state="visible", timeout=15000)
            checks.append({"name": "login_page", "ok": login_form.is_visible()})

            page.fill("#user", user)
            page.click("#btn-next")
            step2 = page.locator("#step-2")
            try:
                step2.wait_for(state="visible", timeout=10000)
                step2_visible = True
            except Exception:
                step2_visible = False
                err = page.locator("#dynamic-error").inner_text(timeout=1000) if page.locator("#dynamic-error").is_visible() else ""
            check2: dict[str, Any] = {"name": "login_step2", "ok": step2_visible}
            if not step2_visible and err:
                check2["error"] = err.strip()
            checks.append(check2)

            if step2_visible:
                page.fill("#pass", password)
                page.locator("#login-form").evaluate("form => form.submit()")
                page.wait_for_load_state("networkidle", timeout=30000)
                logged_in = login_form.count() == 0 or not login_form.is_visible()
                checks.append({"name": "login_submit", "ok": logged_in, "url": page.url})
            else:
                checks.append({"name": "login_submit", "ok": False, "reason": "step2_no_visible"})

            browser.close()
    finally:
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()

    ok = all(c.get("ok") for c in checks)
    return {"ok": ok, "base_url": base, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description="Playwright smoke HL-Go")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    try:
        result = run_checks(headed=args.headed)
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        for check in result.get("checks", []):
            mark = "OK" if check.get("ok") else "FAIL"
            print(f"[{mark}] {check.get('name')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
