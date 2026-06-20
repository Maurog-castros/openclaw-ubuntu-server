"""Browser Playwright para ChileTrabajos (sesion persistente como LinkedIn)."""

from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from jobs_common import ROOT, load_config
from jobs_linkedin_browser import USER_AGENT, credentials_env_path, launch_browser

BASE = "https://www.chiletrabajos.cl"
LOGIN_URL = f"{BASE}/chtlogin"
HOME_URL = f"{BASE}/encuentra-un-empleo"


def storage_state_path(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_config()
    raw = (cfg.get("chiletrabajos") or {}).get("storage_state") or "secrets/chiletrabajos_storage_state.json"
    path = Path(raw)
    return path if path.is_absolute() else ROOT / raw


def load_chiletrabajos_credentials(path: Path | None = None) -> tuple[str, str] | None:
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
        values.get("chiletrabajos_account_email")
        or values.get("chiletrabajos_email")
        or values.get("CHILETRABAJOS_EMAIL")
        or values.get("linkedin_account_email")
        or values.get("LINKEDIN_EMAIL")
    )
    password = (
        values.get("chiletrabajos_account_passwd")
        or values.get("chiletrabajos_password")
        or values.get("CHILETRABAJOS_PASSWORD")
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
        "locale": cfg.get("locale") or "es-CL",
        "user_agent": USER_AGENT,
    }
    if state.exists():
        kwargs["storage_state"] = str(state)
    return browser.new_context(**kwargs)


def is_logged_in(page: Any) -> bool:
    url = page.url.lower()
    if "chtlogin" in url or "form_validation" in url:
        return False
    try:
        html = page.content().lower()
        if "usuario y/o contrase" in html and "incorrect" in html:
            return False
    except Exception:
        return False
    try:
        nav_login = page.locator('a.login[href*="chtlogin"], a.nav-link.login[href*="chtlogin"]')
        if nav_login.count() > 0 and nav_login.first.is_visible():
            return False
    except Exception:
        pass
    try:
        body = page.inner_text("body").lower()
    except Exception:
        body = ""
    if any(x in body for x in ("cerrar sesi", "mis postulaciones", "mi curriculum", "mis alertas", "mi cuenta")):
        return True
    # Sin link "Ingresa a tu cuenta" en nav => sesion activa (mismo criterio que LinkedIn li_at).
    return "chiletrabajos.cl" in url


def save_session_if_logged_in(page: Any, cfg: dict[str, Any] | None = None) -> Path | None:
    """Guarda storage_state solo si hay sesion autenticada."""
    if not is_logged_in(page):
        return None
    return save_session(page, cfg, require_logged_in=False)


def save_session(page: Any, cfg: dict[str, Any] | None = None, *, require_logged_in: bool = True) -> Path:
    cfg = cfg or load_config()
    if require_logged_in and not is_logged_in(page):
        raise RuntimeError("No se guardo sesion: login no completado (aun aparece 'Ingresa a tu cuenta').")
    path = storage_state_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    page.context.storage_state(path=str(path))
    return path


def ensure_login(page: Any, cfg: dict[str, Any] | None = None) -> Path | None:
    """Garantiza sesion activa. Si login OK, persiste storage_state y devuelve la ruta."""
    cfg = cfg or load_config()
    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    if is_logged_in(page):
        return save_session_if_logged_in(page, cfg)

    credentials = load_chiletrabajos_credentials()
    if not credentials:
        raise RuntimeError(
            "Sin credenciales ChileTrabajos en data/secrets/.env. "
            "Agrega chiletrabajos_account_email/chiletrabajos_account_passwd."
        )

    email, password = credentials
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=90000)
    try:
        page.wait_for_selector("#username, input[name='username']", timeout=15000)
        page.fill("#username, input[name='username']", email)
        page.fill("#password, input[name='password']", password)
        page.click("input[name='login'], input[type='submit'][name='login']")
        page.wait_for_load_state("domcontentloaded", timeout=90000)
        time.sleep(2)
        body_lower = page.content().lower()
        if "contrase" in body_lower and "incorrect" in body_lower:
            raise RuntimeError(
                "Credenciales ChileTrabajos invalidas en data/secrets/.env. "
                "Revisa chiletrabajos_account_email y chiletrabajos_account_passwd."
            )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "ChileTrabajos no mostro formulario de login en headless. "
            "Ejecuta login manual headed."
        ) from exc

    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    saved = save_session_if_logged_in(page, cfg)
    if saved:
        return saved

    raise RuntimeError(
        "Sin sesion ChileTrabajos (credenciales invalidas o captcha). Ejecuta:\n"
        "  xvfb-run -a .venv-linkedin-intel/bin/python scripts/jobs_chiletrabajos_login.py login --headed"
    )


class ChileTrabajosFetcher:
    """Fetch HTML reutilizando cookies de sesion Playwright."""

    def __init__(self, page: Any) -> None:
        self.page = page

    def fetch_html(self, url: str, timeout: int = 45) -> str:
        self.page.goto(url, wait_until="domcontentloaded", timeout=max(timeout, 15) * 1000)
        time.sleep(0.8)
        return self.page.content()


@contextmanager
def chiletrabajos_session(cfg: dict[str, Any] | None = None, *, headless: bool = True) -> Iterator[ChileTrabajosFetcher]:
    from playwright.sync_api import sync_playwright

    cfg = cfg or load_config()
    ct = cfg.get("chiletrabajos") or {}
    headless = bool(ct.get("headless", headless))
    with sync_playwright() as playwright:
        browser = launch_browser(playwright, headless=headless)
        context = new_context(browser, cfg)
        page = context.new_page()
        try:
            ensure_login(page, cfg)
            yield ChileTrabajosFetcher(page)
        finally:
            save_session_if_logged_in(page, cfg)
            context.close()
            browser.close()
