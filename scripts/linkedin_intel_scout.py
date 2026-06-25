"""Intel LinkedIn scout — solo lectura: feed, busqueda por keywords y competidores."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv

from linkedin_intel_region import chile_score, is_job_noise, rank_signals, region_cfg
from runtime_paths import repo_root, secrets_dir

ROOT = repo_root()
DEFAULT_CONFIG = ROOT / "config/linkedin_intel/config.json"
INTEL_DATA = ROOT / "data/workspace/marketing/intel/data"
INTEL_REPORTS = ROOT / "data/workspace/marketing/intel/reports"
DRAFTS_DIR = ROOT / "data/workspace/marketing/content/drafts/linkedin"
ENV_CANDIDATES = [
    secrets_dir() / "linkedin_innovacionradical.env",
    Path("/home/node/.openclaw-secrets/linkedin_innovacionradical.env"),
]
RELEVANT = [
    "devops", "sre", "agent", "agents", "ia", "ai", "llm", "mlops", "rag",
    "kubernetes", "observability", "opentelemetry", "finops", "cloud", "platform",
    "machine learning", "modelo", "modelos", "automation", "ci/cd", "dora",
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def load_env() -> None:
    for path in ENV_CANDIDATES:
        if path.exists():
            load_dotenv(path)
            return
    load_dotenv(secrets_dir() / "linkedin_innovacionradical.env")


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Config no encontrada: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


def score_text(text: str) -> int:
    low = text.lower()
    return sum(2 for t in RELEVANT if t in low)


def launch_browser(playwright: Any, headed: bool, headless_cfg: bool) -> Any:
    headless = headless_cfg and not headed
    launch_args = ["--disable-blink-features=AutomationControlled"]
    chrome_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]
    for chrome in chrome_paths:
        if Path(chrome).exists():
            return playwright.chromium.launch(
                headless=headless,
                executable_path=chrome,
                args=launch_args,
            )
    try:
        return playwright.chromium.launch(headless=headless, channel="chrome", args=launch_args)
    except Exception:
        return playwright.chromium.launch(headless=headless, args=launch_args)


def is_session_active(url: str) -> bool:
    low = url.lower()
    if any(x in low for x in ("login", "checkpoint", "authwall", "uas/login")):
        return False
    return any(x in low for x in ("/feed", "/mynetwork", "/messaging", "/notifications", "/in/"))


def has_li_at_cookie(context: Any) -> bool:
    try:
        cookies = context.cookies()
        return any(c.get("name") == "li_at" and c.get("value") for c in cookies)
    except Exception:
        return False


def session_detected(context: Any) -> tuple[bool, str]:
    for p in context.pages:
        try:
            url = p.url
            if is_session_active(url):
                return True, url
        except Exception:
            continue
    if has_li_at_cookie(context):
        return True, "(cookie li_at presente)"
    return False, ""


def save_session(context: Any, storage_state: Path) -> None:
    storage_state.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(storage_state))


def enter_pressed() -> bool:
    try:
        import msvcrt
        while msvcrt.kbhit():
            if msvcrt.getwch() in ("\r", "\n"):
                return True
    except ImportError:
        pass
    return False


def wait_for_manual_login(page, storage_state: Path, login_wait_sec: int) -> None:
    """Abre LinkedIn una vez y espera a que el usuario inicie sesion manualmente."""
    context = page.context
    print("")
    print("=" * 62)
    print("  LOGIN MANUAL — Innovacion Radical / LinkedIn")
    print("=" * 62)
    print("  1. Usa SOLO la ventana Chromium que abrio este script")
    print("  2. Ingresa usuario y contrasena ahi (no otro Chrome/Edge)")
    print("  3. Completa captcha o 2FA si LinkedIn lo solicita")
    print("  4. Cuando veas tu feed, presiona ENTER en esta terminal")
    print(f"  (Auto-detect cada 3s; max {login_wait_sec // 60} min)")
    print("=" * 62)
    print("")

    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=90000)

    deadline = time.time() + login_wait_sec
    last_urls: set[str] = set()
    user_confirmed = False

    while time.time() < deadline:
        if enter_pressed():
            user_confirmed = True
            print("  ENTER recibido — guardando sesion...")
            break

        for p in context.pages:
            try:
                url = p.url[:120]
            except Exception:
                continue
            if url not in last_urls:
                print(f"  Pagina: {url}")
                last_urls.add(url)

        ok, detail = session_detected(context)
        if ok:
            save_session(context, storage_state)
            print("")
            print(f"  Sesion detectada ({detail})")
            print(f"  Guardada en: {storage_state}")
            return

        time.sleep(3)

    ok, detail = session_detected(context)
    if not ok and user_confirmed:
        try:
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
        except Exception:
            pass
        ok, detail = session_detected(context)

    if ok or has_li_at_cookie(context):
        save_session(context, storage_state)
        print("")
        print(f"  Sesion guardada ({detail or 'cookie li_at'})")
        print(f"  Archivo: {storage_state}")
        return

    urls = []
    for p in context.pages:
        try:
            urls.append(p.url)
        except Exception:
            pass
    raise RuntimeError(
        "No se detecto sesion LinkedIn. "
        f"URLs abiertas: {urls}. "
        "Logueate en la ventana Chromium del script y vuelve a intentar."
    )


def ensure_logged_in(page, storage_state: Path, login_wait_sec: int, *, manual: bool = False) -> None:
    if manual:
        wait_for_manual_login(page, storage_state, login_wait_sec)
        return

    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=90000)
    time.sleep(3)
    if is_session_active(page.url) or has_li_at_cookie(page.context):
        return

    raise RuntimeError(
        "No hay sesion LinkedIn activa. Corre primero: "
        "python scripts/linkedin_intel_scout.py login"
    )


def new_browser_context(browser: Any, storage_state: Path) -> Any:
    kwargs: dict[str, Any] = {
        "viewport": {"width": 1400, "height": 900},
        "locale": "es-CL",
        "user_agent": USER_AGENT,
    }
    if storage_state.exists():
        kwargs["storage_state"] = str(storage_state)
    return browser.new_context(**kwargs)


def scroll_page(page: Any, times: int = 4) -> None:
    for _ in range(times):
        page.mouse.wheel(0, 2800)
        time.sleep(1.8)


def guess_author(text: str) -> str:
    m = re.search(r"(?:Publicaci[oó]n en el feed|Feed post)\s+(.+?)\s+•", text, re.I)
    if m:
        return m.group(1).strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    first = lines[0]
    if len(first) <= 70 and not first.lower().startswith(("http", "www.", "publicaci")):
        return first
    return ""


def js_extract_posts(keywords: list[str]) -> str:
    kw = json.dumps(keywords + RELEVANT[:12])
    return f"""
() => {{
  const keywords = {kw}.map(k => k.toLowerCase());
  const match = (t) => {{
    const low = t.toLowerCase();
    return keywords.some(k => low.includes(k));
  }};
  const out = [];
  const seen = new Set();
  for (const el of document.querySelectorAll('div, article, li, section, p')) {{
    const t = (el.innerText || '').replace(/\\s+/g, ' ').trim();
    if (t.length < 90 || t.length > 2200) continue;
    if (!match(t)) continue;
    const key = t.slice(0, 140);
    if (seen.has(key)) continue;
    seen.add(key);
    let url = '';
    const link = el.querySelector('a[href*="/feed/update/"], a[href*="/posts/"], a[href*="linkedin.com/pulse/"]');
    if (link) url = link.href;
    out.push({{ text: t.slice(0, 900), url }});
    if (out.length >= 25) break;
  }}
  return out;
}}
"""


def dedupe_nested_posts(posts: list[dict[str, str]]) -> list[dict[str, str]]:
    ordered = sorted(posts, key=lambda p: len(p.get("text", "")), reverse=True)
    kept: list[dict[str, str]] = []
    for post in ordered:
        text = post.get("text", "")
        if any(text in other.get("text", "") and text != other.get("text", "") for other in kept):
            continue
        kept.append(post)
    return kept


def extract_post_cards(page: Any, limit: int, keywords: list[str] | None = None) -> list[dict[str, str]]:
    keywords = keywords or RELEVANT[:8]
    scroll_page(page, times=5)
    raw = page.evaluate(js_extract_posts(keywords))
    posts: list[dict[str, str]] = []
    for item in raw[: limit * 2]:
        text = re.sub(r"\s+", " ", str(item.get("text", ""))).strip()
        if len(text) < 90:
            continue
        posts.append(
            {
                "author": guess_author(text),
                "text": text[:900],
                "url": str(item.get("url") or ""),
                "source": "linkedin",
            }
        )
    return dedupe_nested_posts(posts)[:limit]


def search_content(page, keyword: str, limit: int, keywords: list[str], cfg: dict[str, Any]) -> list[dict[str, str]]:
    url = build_search_url(keyword, cfg)
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    time.sleep(5)
    items = extract_post_cards(page, limit, keywords=[keyword] + keywords)
    for item in items:
        item["keyword"] = keyword
        item["source"] = f"search:{keyword}"
    return items


def scan_company_posts(page, company_url: str, limit: int, keywords: list[str]) -> list[dict[str, str]]:
    posts_url = company_url.rstrip("/") + "/posts/?viewAsMember=true"
    page.goto(posts_url, wait_until="domcontentloaded", timeout=90000)
    time.sleep(5)
    items = extract_post_cards(page, limit, keywords=keywords)
    for item in items:
        item["source"] = "company_page"
    return items


def dedupe_posts(posts: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for p in posts:
        key = (p.get("url") or p.get("text", ""))[:200]
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def rank_posts(posts: list[dict[str, str]], cfg: dict[str, Any] | None = None) -> list[dict[str, str]]:
    return rank_signals(posts, cfg, base_score_fn=score_text)


def build_search_url(keyword: str, cfg: dict[str, Any]) -> str:
    region = region_cfg(cfg)
    geo = region.get("geo_urn")
    base = (
        "https://www.linkedin.com/search/results/content/?"
        f"keywords={quote_plus(keyword)}&origin=GLOBAL_SEARCH_HEADER"
    )
    if geo:
        base += f"&geoUrn=%5B%22{geo}%22%5D"
    lang = region.get("language")
    if lang:
        base += f"&language={quote_plus(str(lang))}"
    return base


def build_report(posts: list[dict[str, str]], cfg: dict[str, Any]) -> str:
    today = date.today().isoformat()
    lines = [
        f"# LinkedIn Intel — {today}",
        "",
        f"Empresa: [{cfg.get('company_name')}]({cfg.get('company_page_url')})",
        "",
        "## TL;DR",
        f"- {len(posts)} senales relevantes detectadas en LinkedIn.",
        "- Modo: solo lectura (sin publicar).",
        "",
        "## Senales top",
    ]
    for i, p in enumerate(posts[:12], 1):
        author = p.get("author") or "Autor desconocido"
        src = p.get("source", "")
        kw = p.get("keyword", "")
        text = p.get("text", "").replace("\n", " ")
        url = p.get("url", "")
        chile = " 🇨🇱" if chile_score(text, cfg) > 0 else ""
        meta = f" ({src}" + (f", {kw}" if kw else "") + ")"
        link = f" — [{url}]({url})" if url else ""
        lines.append(f"{i}. **{author}**{meta}{chile}: {text[:280]}{link}")
    lines.extend(["", "## Borradores sugeridos (publicacion manual)", ""])
    if not posts:
        lines.append("_Sin senales en este scan. Revisa sesion LinkedIn o vuelve a correr scan._")
    for i, p in enumerate(posts[:4], 1):
        snippet = p.get("text", "")[:120].replace("\n", " ")
        lines.append(
            f"### Borrador {i}\n"
            f"- **Hook:** Lo que esta pasando en {p.get('keyword') or 'DevOps Chile'} esta semana\n"
            f"- **Angulo Innovacion Radical:** DevOps + IA enterprise Chile (DORA, costos, incidentes reales)\n"
            f"- **Sustento:** reaccion a senal — \"{snippet}...\"\n"
            f"- **CTA:** Comenta si quieres el checklist / DM para auditoria\n"
        )
    return "\n".join(lines) + "\n"


def cmd_login(cfg: dict[str, Any], headed: bool, login_wait_sec: int) -> int:
    storage_state = resolve_path(cfg["storage_state"])
    load_env()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch_browser(p, headed=headed, headless_cfg=True)
        context_kwargs: dict[str, Any] = {}
        if storage_state.exists():
            context_kwargs["storage_state"] = str(storage_state)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        ensure_logged_in(page, storage_state, login_wait_sec, manual=True)
        browser.close()
    print(f"Sesion LinkedIn guardada: {storage_state}")
    return 0


def cmd_scan(cfg: dict[str, Any], headed: bool, login_wait_sec: int, json_out: bool) -> int:
    storage_state = resolve_path(cfg["storage_state"])
    if not storage_state.exists():
        raise SystemExit(
            f"Sin sesion LinkedIn ({storage_state}). "
            "Corre primero: python scripts/linkedin_intel_scout.py login --headed"
        )
    load_env()
    from playwright.sync_api import sync_playwright

    all_posts: list[dict[str, str]] = []
    pause = int(cfg.get("pause_between_searches_sec", 6))
    headless = cfg.get("headless", True) and not headed

    with sync_playwright() as p:
        browser = launch_browser(p, headed=headed, headless_cfg=headless)
        context = browser.new_context(
            storage_state=str(storage_state),
            viewport={"width": 1400, "height": 900},
            locale="es-CL",
            user_agent=USER_AGENT,
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()
        if storage_state.exists():
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=90000)
            time.sleep(4)
        else:
            ensure_logged_in(page, storage_state, login_wait_sec)

        keywords = list(cfg.get("keywords") or RELEVANT[:8])
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=90000)
        time.sleep(4)
        feed_limit = int(cfg.get("max_feed_posts", 15))
        feed_posts = extract_post_cards(page, feed_limit, keywords=keywords)
        for item in feed_posts:
            item["source"] = "feed"
        all_posts.extend(feed_posts)

        search_keywords = keywords[:6]
        for kw in search_keywords:
            all_posts.extend(
                search_content(page, kw, int(cfg.get("max_posts_per_keyword", 5)), keywords, cfg)
            )
            time.sleep(pause)

        for comp in cfg.get("competitors", []):
            all_posts.extend(scan_company_posts(page, comp, 5, keywords))
            time.sleep(pause)

        context.storage_state(path=str(storage_state))
        browser.close()

    ranked = rank_posts(dedupe_posts(all_posts), cfg)
    ranked = [p for p in ranked if score_text(p.get("text", "")) > 0 and not is_job_noise(p.get("text", ""), cfg)][:40]
    if not ranked:
        ranked = rank_posts(dedupe_posts(all_posts), cfg)[:15]

    INTEL_DATA.mkdir(parents=True, exist_ok=True)
    INTEL_REPORTS.mkdir(parents=True, exist_ok=True)
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    json_path = INTEL_DATA / f"linkedin_signals_{today}.json"
    md_path = INTEL_REPORTS / f"{today}-linkedin-intel.md"
    draft_path = DRAFTS_DIR / f"{today}-linkedin-drafts.md"

    payload = {
        "status": "ok",
        "date": today,
        "company": cfg.get("company_name"),
        "signal_count": len(ranked),
        "signals": ranked,
        "report_path": str(md_path.relative_to(ROOT)),
        "draft_path": str(draft_path.relative_to(ROOT)),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md = build_report(ranked, cfg)
    md_path.write_text(report_md, encoding="utf-8")
    draft_path.write_text(report_md, encoding="utf-8")

    if json_out:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Senales: {len(ranked)} -> {json_path}")
        print(f"Reporte: {md_path}")
        print(f"Borradores: {draft_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Intel LinkedIn scout (solo lectura).")
    parser.add_argument("command", choices=["login", "scan"], nargs="?", default="scan")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--headed", action="store_true", help="Navegador visible (recomendado para login)")
    parser.add_argument("--headless", action="store_true", help="Sin ventana (solo scan automatico)")
    parser.add_argument("--login-wait-sec", type=int, default=600)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    cfg = load_config(Path(args.config))
    headed = args.headed or (args.command == "login" and not args.headless)
    if args.command == "login":
        raise SystemExit(cmd_login(cfg, headed, args.login_wait_sec))
    raise SystemExit(cmd_scan(cfg, headed, args.login_wait_sec, args.json))


if __name__ == "__main__":
    main()
