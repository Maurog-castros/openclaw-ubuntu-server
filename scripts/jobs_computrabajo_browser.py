"""Browser Playwright para Computrabajo candidato (sesion persistente)."""

from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from jobs_common import load_config
from jobs_linkedin_browser import USER_AGENT, credentials_env_path, launch_browser
from runtime_paths import resolve_repo_path

CANDIDATE_BASE = "https://candidato.cl.computrabajo.com"
LOGIN_URL = f"{CANDIDATE_BASE}/acceso/"
HOME_URL = f"{CANDIDATE_BASE}/candidate/home"


def computrabajo_portal_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    raw = cfg.get("computrabajo") or {}
    return {
        "storage_state": str(raw.get("storage_state") or "runtime/secrets/computrabajo_storage_state.json"),
        "login_url": str(raw.get("login_url") or LOGIN_URL),
        "home_url": str(raw.get("home_url") or HOME_URL),
        "headless": bool(raw.get("headless", True)),
    }


def storage_state_path(cfg: dict[str, Any] | None = None) -> Path:
    return resolve_repo_path(computrabajo_portal_cfg(cfg)["storage_state"])


def load_computrabajo_credentials(path: Path | None = None) -> tuple[str, str] | None:
    path = path or credentials_env_path()
    if not path.exists():
        return None
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    email = (
        values.get("computrabajo_account_email")
        or values.get("computrabajo_email")
        or values.get("COMPUTRABAJO_EMAIL")
        or values.get("linkedin_account_email")
        or values.get("LINKEDIN_EMAIL")
    )
    password = (
        values.get("computrabajo_account_passwd")
        or values.get("computrabajo_password")
        or values.get("COMPUTRABAJO_PASSWORD")
        or values.get("linkedin_account_passwd")
        or values.get("LINKEDIN_PASSWORD")
    )
    if not email or not password:
        return None
    return email, password


def new_context(browser: Any, cfg: dict[str, Any] | None = None) -> Any:
    cfg = cfg or load_config()
    state = storage_state_path(cfg)
    kwargs: dict[str, Any] = {
        "viewport": {"width": 1400, "height": 900},
        "locale": (cfg.get("locale") or "es-CL"),
        "user_agent": USER_AGENT,
    }
    if state.exists():
        kwargs["storage_state"] = str(state)
    return browser.new_context(**kwargs)


def is_logged_in(page: Any) -> bool:
    url = (page.url or "").lower()
    if "/acceso" in url or "login" in url:
        return False
    try:
        body = page.inner_text("body").lower()
    except Exception:
        body = ""
    markers = (
        "mis postulaciones",
        "mi curriculum",
        "mi currículum",
        "cerrar sesi",
        "cerrar sesión",
        "alertas de empleo",
        "candidate/home",
    )
    if any(marker in body or marker in url for marker in markers):
        return True
    return "candidato.cl.computrabajo.com/candidate" in url


def save_session_if_logged_in(page: Any, cfg: dict[str, Any] | None = None) -> Path | None:
    if not is_logged_in(page):
        return None
    return save_session(page, cfg, require_logged_in=False)


def save_session(page: Any, cfg: dict[str, Any] | None = None, *, require_logged_in: bool = True) -> Path:
    cfg = cfg or load_config()
    if require_logged_in and not is_logged_in(page):
        raise RuntimeError("No se guardo sesion Computrabajo: login no completado.")
    path = storage_state_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    page.context.storage_state(path=str(path))
    return path


def _click_first(page: Any, selectors: list[str], timeout: int = 8000) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible():
                locator.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


def submit_login_form(page: Any, email: str, password: str) -> None:
    portal = computrabajo_portal_cfg()
    page.goto(portal["login_url"], wait_until="domcontentloaded", timeout=90000)
    time.sleep(1.5)
    page.fill("#Email, input[name='Email']", email)
    time.sleep(0.5)
    _click_first(
        page,
        [
            "#sbLoginEmail",
            "a[btn-submit]:visible",
            "button:has-text('Continuar')",
            "a:has-text('Continuar')",
        ],
    )
    page.wait_for_selector("#password, input[name='Password']", state="visible", timeout=20000)
    page.fill("#password, input[name='Password']", password)
    time.sleep(0.5)
    _click_first(
        page,
        [
            "#sbLogin",
            "a[btn-submit]:visible",
            "button:has-text('Iniciar')",
            "a:has-text('Iniciar sesión')",
            "a:has-text('Entrar')",
        ],
    )
    page.wait_for_load_state("domcontentloaded", timeout=90000)
    time.sleep(2)


def ensure_login(page: Any, cfg: dict[str, Any] | None = None) -> Path | None:
    cfg = cfg or load_config()
    portal = computrabajo_portal_cfg(cfg)
    page.goto(portal["home_url"], wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    if is_logged_in(page):
        return save_session_if_logged_in(page, cfg)

    credentials = load_computrabajo_credentials()
    if not credentials:
        raise RuntimeError(
            "Sin credenciales Computrabajo en runtime/secrets/.env. "
            "Agrega computrabajo_account_email y computrabajo_account_passwd."
        )

    email, password = credentials
    submit_login_form(page, email, password)
    body_lower = page.content().lower()
    if "contrase" in body_lower and ("incorrect" in body_lower or "no coincide" in body_lower):
        raise RuntimeError(
            "Credenciales Computrabajo invalidas en runtime/secrets/.env. "
            "Revisa computrabajo_account_email y computrabajo_account_passwd."
        )

    page.goto(portal["home_url"], wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    saved = save_session_if_logged_in(page, cfg)
    if saved:
        return saved

    raise RuntimeError(
        "Sin sesion Computrabajo (credenciales invalidas, captcha o MFA). Ejecuta:\n"
        "  xvfb-run -a .venv-linkedin-intel/bin/python scripts/jobs_computrabajo_login.py login --headed"
    )


@contextmanager
def computrabajo_session(cfg: dict[str, Any] | None = None, *, headless: bool = True) -> Iterator[Any]:
    from playwright.sync_api import sync_playwright

    cfg = cfg or load_config()
    portal = computrabajo_portal_cfg(cfg)
    headless = bool(portal.get("headless", headless))
    with sync_playwright() as playwright:
        browser = launch_browser(playwright, headless=headless)
        context = new_context(browser, cfg)
        page = context.new_page()
        try:
            ensure_login(page, cfg)
            yield page
        finally:
            save_session_if_logged_in(page, cfg)
            context.close()
            browser.close()
