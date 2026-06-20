"""Browser Playwright para Laborum (sesion persistente como LinkedIn/ChileTrabajos)."""

from __future__ import annotations

import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from jobs_common import load_config
from jobs_linkedin_browser import USER_AGENT, credentials_env_path, launch_browser
from runtime_paths import resolve_repo_path

DISPLAY = os.environ.get("DISPLAY", "")
BASE = "https://www.laborum.cl"
LOGIN_URL = f"{BASE}/login?returnTo=/candidatos/curriculum"
CURRICULUM_URL = f"{BASE}/candidatos/curriculum"


def laborum_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    raw = (cfg.get("job_portals") or {}).get("laborum") or {}
    return {
        "storage_state": str(raw.get("storage_state") or "runtime/secrets/laborum_storage_state.json"),
        "curriculum_url": str(raw.get("curriculum_url") or CURRICULUM_URL),
        "login_url": str(raw.get("login_url") or LOGIN_URL),
        "headless": bool(raw.get("headless", cfg.get("headless", True))),
        "auto_login": bool(raw.get("auto_login", False)),
    }


def storage_state_path(cfg: dict[str, Any] | None = None) -> Path:
    return resolve_repo_path(laborum_cfg(cfg)["storage_state"])


def load_laborum_credentials(path: Path | None = None) -> tuple[str, str] | None:
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
        values.get("laborum_account_email")
        or values.get("laborum_email")
        or values.get("LABORUM_EMAIL")
    )
    password = (
        values.get("laborum_account_passwd")
        or values.get("laborum_password")
        or values.get("LABORUM_PASSWORD")
    )
    if not email or not password:
        return None
    return email, password


def launch_laborum_browser(playwright: Any, *, headless: bool) -> Any:
    # Cloudflare bloquea headless puro; preferir headed+xvfb si no hay DISPLAY.
    if headless and not DISPLAY:
        headless = False
    return launch_browser(playwright, headless=headless)


def new_context(browser: Any, cfg: dict[str, Any] | None = None) -> Any:
    cfg = cfg or load_config()
    state = storage_state_path(cfg)
    kwargs: dict[str, Any] = {
        "viewport": {"width": 1400, "height": 900},
        "locale": cfg.get("locale") or "es-CL",
        "user_agent": USER_AGENT,
    }
    if state.exists():
        kwargs["storage_state"] = str(state)
    return browser.new_context(**kwargs)


def is_logged_in(page: Any) -> bool:
    url = page.url.lower()
    if "/login" in url or "ingresar" in url:
        return False
    if _needs_mfa(page):
        return False
    try:
        html = page.content().lower()
        if any(x in html for x in ("contraseña incorrecta", "password incorrect", "credenciales invalidas", "credenciales inválidas")):
            return False
    except Exception:
        return False
    try:
        login_cta = page.get_by_role("link", name="Ingresar")
        if login_cta.count() > 0 and login_cta.first.is_visible():
            return False
    except Exception:
        pass
    try:
        body = page.inner_text("body").lower()
    except Exception:
        body = ""
    if "ingresa a tu cuenta" in body and "olvid" in body:
        return False
    if any(x in body for x in ("cerrar sesi", "mis postulaciones", "mi cv", "mi curriculum", "curriculum vitae")):
        return True
    return any(x in url for x in ("/candidatos/curriculum", "/candidatos/perfil", "/candidatos/postulaciones"))


def save_session(page: Any, cfg: dict[str, Any] | None = None, *, require_logged_in: bool = True) -> Path:
    cfg = cfg or load_config()
    if require_logged_in and not is_logged_in(page):
        raise RuntimeError("No se guardo sesion Laborum: login no completado.")
    path = storage_state_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    page.context.storage_state(path=str(path))
    return path


def save_session_if_logged_in(page: Any, cfg: dict[str, Any] | None = None) -> Path | None:
    if not is_logged_in(page):
        return None
    return save_session(page, cfg, require_logged_in=False)


def _needs_mfa(page: Any) -> bool:
    try:
        body = page.inner_text("body").lower()
    except Exception:
        return False
    return "código de acceso" in body or "codigo de acceso" in body or "ingresar código" in body


def _submit_login_form(page: Any, email: str, password: str) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=90000)
    time.sleep(2)
    page.locator("#email, input[type='email']").first.fill(email)
    page.locator("input[type='password']").first.fill(password)
    page.locator("button:has-text('Ingresar')").first.click()
    page.wait_for_load_state("domcontentloaded", timeout=90000)
    time.sleep(4)


def _submit_mfa_code(page: Any, code: str) -> None:
    code = re.sub(r"\D", "", code or "")
    if len(code) != 6:
        raise RuntimeError("Codigo MFA Laborum debe tener 6 digitos.")
    page.wait_for_load_state("domcontentloaded", timeout=90000)
    time.sleep(1)
    mfa_input = page.locator("input[name='codigo']")
    if not mfa_input.count():
        mfa_input = page.locator(
            "input[maxlength='6']:not([type='password']):not([type='email']), input[autocomplete='one-time-code']"
        )
    if not mfa_input.count():
        raise RuntimeError("No encontre campo para codigo MFA en Laborum.")
    field = mfa_input.first
    field.fill(code)
    field.press("Enter")
    page.wait_for_load_state("domcontentloaded", timeout=90000)
    time.sleep(4)
    if _needs_mfa(page):
        page.get_by_role("button", name="Ingresar", exact=True).last.click()
        page.wait_for_load_state("domcontentloaded", timeout=90000)
        time.sleep(5)


def ensure_login(
    page: Any,
    cfg: dict[str, Any] | None = None,
    *,
    mfa_code: str | None = None,
    mfa_from_gmail: bool = False,
    auto_submit: bool = False,
) -> Path | None:
    """Garantiza sesion activa. Por defecto NO hace auto-login (evita spam MFA por email)."""
    cfg = cfg or load_config()
    lb = laborum_cfg(cfg)
    page.goto(lb["curriculum_url"], wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    if is_logged_in(page):
        return save_session_if_logged_in(page, cfg)

    if not auto_submit:
        raise RuntimeError(
            "Sin sesion Laborum. Login manual (no dispara emails automaticos):\n"
            "  xvfb-run -a .venv-jobs-portals/bin/python scripts/jobs_laborum_login.py login --headed\n"
            "Luego reintenta sync/scrape."
        )

    credentials = load_laborum_credentials()
    if not credentials:
        raise RuntimeError(
            "Sin credenciales Laborum en data/secrets/.env. "
            "Agrega laborum_account_email y laborum_account_passwd."
        )

    email, password = credentials
    mfa_trigger_ms = int(time.time() * 1000)
    page.goto(lb["login_url"], wait_until="domcontentloaded", timeout=90000)
    try:
        _submit_login_form(page, email, password)
        if _needs_mfa(page):
            if not mfa_code and mfa_from_gmail:
                from jobs_laborum_mfa_gmail import wait_for_laborum_mfa_code

                mfa_code = wait_for_laborum_mfa_code(not_before_ms=mfa_trigger_ms - 5000, wait_sec=120)
            if not mfa_code:
                raise RuntimeError(
                    "Laborum pidio codigo MFA por email. Pasa --mfa-code, laborum_mfa_code en .env, "
                    "o deja --mfa-from-gmail (default) con Gmail OAuth activo."
                )
            _submit_mfa_code(page, mfa_code)
        html = page.content().lower()
        if any(x in html for x in ("contraseña incorrecta", "password incorrect", "credenciales invalidas")):
            raise RuntimeError(
                "Credenciales Laborum invalidas en data/secrets/.env. "
                "Revisa laborum_account_email y laborum_account_passwd."
            )
    except RuntimeError:
        raise
    except Exception as exc:
        if _needs_mfa(page):
            raise RuntimeError(f"Fallo al enviar codigo MFA Laborum: {exc}") from exc
        raise RuntimeError(
            "Laborum no mostro formulario de login (Cloudflare/captcha). "
            "Ejecuta login manual headed."
        ) from exc

    page.goto(lb["curriculum_url"], wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    saved = save_session_if_logged_in(page, cfg)
    if saved:
        return saved

    raise RuntimeError(
        "Sin sesion Laborum (credenciales invalidas o captcha). Ejecuta:\n"
        "  xvfb-run -a .venv-jobs-portals/bin/python scripts/jobs_laborum_login.py login --headed"
    )


@contextmanager
def laborum_session(cfg: dict[str, Any] | None = None, *, headless: bool | None = None) -> Iterator[Any]:
    from playwright.sync_api import sync_playwright

    cfg = cfg or load_config()
    lb = laborum_cfg(cfg)
    use_headless = bool(lb["headless"]) if headless is None else headless
    with sync_playwright() as playwright:
        browser = launch_laborum_browser(playwright, headless=use_headless)
        context = new_context(browser, cfg)
        page = context.new_page()
        try:
            ensure_login(page, cfg, auto_submit=bool(laborum_cfg(cfg).get("auto_login")))
            yield page
        finally:
            save_session_if_logged_in(page, cfg)
            context.close()
            browser.close()
