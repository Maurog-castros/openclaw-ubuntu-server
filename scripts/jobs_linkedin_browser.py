"""Browser Playwright para postulaciones LinkedIn (cuenta personal Mauro)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from jobs_common import ROOT, load_config

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def storage_state_path(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_config()
    raw = cfg.get("linkedin_storage_state") or "secrets/linkedin_storage_state.json"
    p = Path(raw)
    return p if p.is_absolute() else ROOT / raw


def credentials_env_path() -> Path:
    return ROOT / "data/secrets/.env"


def load_linkedin_credentials(path: Path | None = None) -> tuple[str, str] | None:
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
    email = values.get("linkedin_account_email") or values.get("LINKEDIN_EMAIL")
    password = values.get("linkedin_account_passwd") or values.get("LINKEDIN_PASSWORD")
    if not email or not password:
        return None
    return email, password


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
    if any(x in url for x in ("login", "authwall", "checkpoint")):
        return False
    try:
        cookies = page.context.cookies()
        if any(c.get("name") == "li_at" and c.get("value") for c in cookies):
            return True
    except Exception:
        pass
    return any(x in url for x in ("/feed", "/jobs", "/in/"))


def ensure_login(page: Any, cfg: dict[str, Any] | None = None) -> None:
    cfg = cfg or load_config()
    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=90000)
    time.sleep(2)
    if is_logged_in(page):
        return
    credentials = load_linkedin_credentials()
    if credentials:
        email, password = credentials
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=90000)
        try:
            page.wait_for_selector("input#username, input[name='session_key']", timeout=15000)
            page.fill("input#username, input[name='session_key']", email)
            page.fill("input#password, input[name='session_password']", password)
        except Exception as exc:
            raise RuntimeError(
                "LinkedIn no mostro formulario de login en headless; probable checkpoint/bloqueo. "
                "Ejecuta login manual headed."
            ) from exc
        page.click("button[type='submit']")
        page.wait_for_load_state("domcontentloaded", timeout=90000)
        time.sleep(4)
        if is_logged_in(page):
            storage_state_path(cfg).parent.mkdir(parents=True, exist_ok=True)
            page.context.storage_state(path=str(storage_state_path(cfg)))
            return
    raise RuntimeError(
        "Sin sesion LinkedIn personal o checkpoint/2FA pendiente. Ejecuta: "
        ".venv-linkedin-intel/bin/python scripts/jobs_linkedin_login.py login --headed"
    )


def build_jobs_search_url(keywords: str, cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    geo = cfg.get("geo_urn") or "104621616"
    location = cfg.get("location_search") or "Chile"
    url = (
        "https://www.linkedin.com/jobs/search/?"
        f"keywords={quote_plus(keywords)}&location={quote_plus(location)}"
        f"&geoId={geo}"
    )
    if cfg.get("easy_apply_only", True):
        url += "&f_AL=true"
    return url


JS_EXTRACT_JOBS = """
() => {
  const out = [];
  const seen = new Set();
  const cards = document.querySelectorAll(
    'div.job-card-container, li.jobs-search-results__list-item, div[data-job-id], a[href*="/jobs/view/"]'
  );
  for (const el of cards) {
    let link = el.querySelector('a[href*="/jobs/view/"]');
    if (!link && el.matches('a[href*="/jobs/view/"]')) link = el;
    if (!link) continue;
    const job_url = link.href.split('?')[0];
    if (seen.has(job_url)) continue;
    seen.add(job_url);
    const titleEl = el.querySelector('.job-card-list__title, .artdeco-entity-lockup__title, strong, h3');
    const companyEl = el.querySelector('.job-card-container__company-name, .artdeco-entity-lockup__subtitle');
    const title = (titleEl?.innerText || link.innerText || '').trim();
    const company = (companyEl?.innerText || '').trim();
    const easy = !!(el.innerText || '').match(/Solicitud sencilla|Easy Apply/i);
    if (!title) continue;
    out.push({ title, company, job_url, easy_apply: easy });
    if (out.length >= 30) break;
  }
  return out;
}
"""
