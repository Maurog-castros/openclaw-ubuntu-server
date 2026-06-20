#!/usr/bin/env python3
"""Scrape vacantes desde chiletrabajos.cl a CSV compatible con el pipeline Jobs."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import ssl
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

from jobs_common import JOBS_WS, load_config, score_vacancy

try:
    from jobs_chiletrabajos_browser import ChileTrabajosFetcher, chiletrabajos_session
except ImportError:
    ChileTrabajosFetcher = None  # type: ignore[misc, assignment]
    chiletrabajos_session = None  # type: ignore[misc, assignment]

BASE = "https://www.chiletrabajos.cl"
USER_AGENT = "Mozilla/5.0 (compatible; OpenClawJobs/1.0; +https://github.com/openclaw)"
PAGE_SIZE = 30

CSV_COLUMNS = [
    "scraped_at",
    "source",
    "job_id",
    "title",
    "company",
    "location",
    "workplace",
    "listed_at",
    "easy_apply",
    "promoted",
    "match_score",
    "job_url",
    "collection_url",
    "summary",
]

JOB_ITEM_RE = re.compile(r'<div class="job-item([^"]*)"[^>]*>(.*?)</div>\s*</div>\s*(?=<div class="job-item|<div class="box|$)', re.S)
TITLE_RE = re.compile(r'class="font-weight-bold">([^<]+)</a>')
URL_RE = re.compile(r'href="(https://www\.chiletrabajos\.cl/trabajo/[^"]+)"')
COMPANY_RE = re.compile(r'<h3 class="meta">\s*([^<\n]+)')
CITY_RE = re.compile(r'/ciudad/([^".]+)\.html')
DATE_RE = re.compile(r'(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})', re.I)
DESC_RE = re.compile(r'<p class="description"[^>]*>(.*?)</p>', re.S)
DETAIL_ROWS_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
DETAIL_CELLS_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
DETAIL_DESC_RE = re.compile(
    r"Descripci.*?oferta.*?</h\d>(.*?)(?:<h\d|Comparte por redes|Estad[ií]sticas del anuncio)",
    re.I | re.S,
)
RSS_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)


def job_id_from_url(url: str) -> str:
    match = re.search(r"-(\d{5,})(?:\?|$|/)", url.rstrip("/"))
    return match.group(1) if match else ""


def clean_text(raw: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    return re.sub(r"\s+", " ", text).strip()


def fetch_html(url: str, timeout: int = 45, fetcher: ChileTrabajosFetcher | None = None) -> str:
    if fetcher is not None:
        return fetcher.fetch_html(url, timeout=timeout)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "es-CL,es;q=0.9"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


def infer_workplace(location: str, summary: str) -> str:
    blob = f"{location} {summary}".lower()
    if "teletrabajo" in blob or "remoto" in blob or "remote" in blob:
        return "remote"
    if "hibrido" in blob or "híbrido" in blob or "hybrid" in blob:
        return "hybrid"
    if "presencial" in blob or "on-site" in blob or "onsite" in blob:
        return "onsite"
    return ""


def listing_url(*, category_slug: str, offset: int = 0, keyword: str = "") -> str:
    path = f"/trabajos/{category_slug}" if category_slug else "/encuentra-un-empleo"
    if offset:
        path = f"{path}/{offset}"
    url = urljoin(BASE, path)
    if keyword:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}palabra={quote(keyword)}"
    return url


def parse_listing_page(page_html: str, scraped_at: str, collection_url: str, cfg: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for block in JOB_ITEM_RE.findall(page_html):
        body = block[1] if isinstance(block, tuple) else block
        url_match = URL_RE.search(body)
        title_match = TITLE_RE.search(body)
        if not url_match or not title_match:
            continue
        job_url = url_match.group(1).split("?")[0].rstrip("/")
        if "/postular/" in job_url:
            continue
        title = clean_text(title_match.group(1))
        company_match = COMPANY_RE.search(body)
        company = clean_text(company_match.group(1)).strip(", ") if company_match else ""
        city_match = CITY_RE.search(body)
        location = city_match.group(1).replace("-", " ").title() if city_match else ""
        if company and location:
            location = f"{location}, Chile"
        elif company:
            location = "Chile"
        date_match = DATE_RE.search(body)
        listed_at = clean_text(date_match.group(1)) if date_match else ""
        desc_match = DESC_RE.search(body)
        summary = clean_text(desc_match.group(1)) if desc_match else ""
        summary = re.sub(r"Ver m[aá]s$", "", summary, flags=re.I).strip()
        text = " ".join(x for x in (title, company, location, summary) if x)
        rows.append(
            {
                "scraped_at": scraped_at,
                "source": "chiletrabajos",
                "job_id": job_id_from_url(job_url),
                "title": title[:200],
                "company": company[:160],
                "location": location[:160],
                "workplace": infer_workplace(location, summary),
                "listed_at": listed_at[:80],
                "easy_apply": "0",
                "promoted": "1" if "destacado" in body else "0",
                "match_score": str(score_vacancy(text, cfg)),
                "job_url": job_url,
                "collection_url": collection_url,
                "summary": summary[:500],
            }
        )
    return rows


def fetch_job_detail(job_url: str, fetcher: ChileTrabajosFetcher | None = None) -> dict[str, str]:
    page = fetch_html(job_url, fetcher=fetcher)
    meta: dict[str, str] = {}
    for row in DETAIL_ROWS_RE.findall(page):
        cells = DETAIL_CELLS_RE.findall(row)
        if len(cells) != 2:
            continue
        key = clean_text(cells[0])
        val = clean_text(cells[1])
        if key:
            meta[key] = val
    desc = ""
    desc_match = DETAIL_DESC_RE.search(page)
    if desc_match:
        desc = clean_text(desc_match.group(1))
    location = meta.get("Ubicación", "")
    if location and "CL" not in location:
        location = f"{location}, Chile"
    title_match = re.search(r"<title>([^|<]+)", page, re.I)
    title = clean_text(title_match.group(1)) if title_match else meta.get("title", "")
    if title.endswith("Chiletrabajos"):
        title = title.rsplit("-", 1)[0].strip()
    blob = f"{title} {desc} {meta.get('Tipo', '')} {meta.get('Categoría', '')}"
    return {
        "title": title[:200],
        "company": meta.get("Buscado", "")[:160],
        "location": location[:160],
        "description": desc,
        "listed_at": meta.get("Fecha", "")[:80],
        "category": meta.get("Categoría", "")[:120],
        "job_type": meta.get("Tipo", "")[:80],
        "workplace": infer_workplace(location, blob),
    }


def scrape_listings(
    *,
    pages: int = 3,
    category_slug: str = "informatica",
    keyword: str = "",
    min_score: int | None = None,
    limit: int = 120,
    fetcher: ChileTrabajosFetcher | None = None,
) -> list[dict[str, str]]:
    cfg = load_config()
    min_score = min_score if min_score is not None else int(cfg.get("min_match_score") or 12)
    scraped_at = datetime.now().astimezone().isoformat(timespec="seconds")
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for page_idx in range(max(1, pages)):
        offset = page_idx * PAGE_SIZE
        url = listing_url(category_slug=category_slug, offset=offset, keyword=keyword)
        try:
            page_html = fetch_html(url, fetcher=fetcher)
        except (urllib.error.URLError, TimeoutError) as exc:
            if page_idx == 0:
                raise RuntimeError(f"No se pudo leer {url}: {exc}") from exc
            break
        batch = parse_listing_page(page_html, scraped_at, url, cfg)
        if not batch:
            break
        for row in batch:
            key = row.get("job_id") or row.get("job_url")
            if not key or key in seen:
                continue
            if int(row.get("match_score") or 0) < min_score:
                continue
            seen.add(key)
            out.append(row)
            if len(out) >= limit:
                return out
    return out


def output_csv_path(run_date: str | None = None) -> Path:
    run_date = run_date or datetime.now().strftime("%Y-%m-%d")
    return JOBS_WS / f"chiletrabajos_{run_date}.csv"


def write_csv(rows: list[dict[str, str]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    latest = path.parent / "chiletrabajos_latest.csv"
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def chiletrabajos_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    raw = cfg.get("chiletrabajos") or {}
    return {
        "category_slug": str(raw.get("category_slug") or "informatica"),
        "category_id": str(raw.get("category_id") or "2007"),
        "pages": int(raw.get("pages") or 4),
        "keyword": str(raw.get("keyword") or ""),
        "min_score": int(raw.get("min_score") or cfg.get("min_match_score") or 12),
        "limit": int(raw.get("limit") or 80),
        "extra_categories": list(raw.get("extra_categories") or []),
        "mode": str(raw.get("mode") or "both"),
        "rss_limit": int(raw.get("rss_limit") or 600),
        "use_session": bool(raw.get("use_session", True)),
        "storage_state": str(raw.get("storage_state") or "secrets/chiletrabajos_storage_state.json"),
        "headless": bool(raw.get("headless", cfg.get("headless", True))),
    }


def rss_url(category_slug: str = "informatica") -> str:
    return urljoin(BASE, f"/rss/{category_slug}")


def parse_rss(xml_text: str, scraped_at: str, collection_url: str, cfg: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in RSS_ITEM_RE.findall(xml_text):
        title_m = re.search(r"<title>(.*?)</title>", item, re.S)
        link_m = re.search(r"<link>(.*?)</link>", item, re.S)
        desc_m = re.search(r"<description>(.*?)</description>", item, re.S)
        guid_m = re.search(r"<guid>(.*?)</guid>", item, re.S)
        if not link_m:
            continue
        job_url = clean_text(link_m.group(1)).split("?")[0].rstrip("/")
        title_raw = clean_text(title_m.group(1) if title_m else "")
        title = title_raw.split("|")[0].strip()
        location = title_raw.split("|")[-1].strip() if "|" in title_raw else "Chile"
        summary = clean_text(desc_m.group(1) if desc_m else "")
        job_id = clean_text(guid_m.group(1) if guid_m else "") or job_id_from_url(job_url)
        text = " ".join(x for x in (title, location, summary) if x)
        rows.append(
            {
                "scraped_at": scraped_at,
                "source": "chiletrabajos",
                "job_id": job_id,
                "title": title[:200],
                "company": "",
                "location": location[:160],
                "workplace": infer_workplace(location, summary),
                "listed_at": "",
                "easy_apply": "0",
                "promoted": "0",
                "match_score": str(score_vacancy(text, cfg)),
                "job_url": job_url,
                "collection_url": collection_url,
                "summary": summary[:500],
            }
        )
    return rows


def scrape_rss(
    *,
    category_slug: str = "informatica",
    min_score: int | None = None,
    limit: int = 120,
    fetcher: ChileTrabajosFetcher | None = None,
) -> list[dict[str, str]]:
    cfg = load_config()
    min_score = min_score if min_score is not None else int(cfg.get("min_match_score") or 12)
    scraped_at = datetime.now().astimezone().isoformat(timespec="seconds")
    url = rss_url(category_slug)
    xml_text = fetch_html(url, timeout=90, fetcher=fetcher)
    rows = parse_rss(xml_text, scraped_at, url, cfg)
    rows.sort(key=lambda item: int(item.get("match_score") or 0), reverse=True)
    out: list[dict[str, str]] = []
    for row in rows:
        if int(row.get("match_score") or 0) < min_score:
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


def merge_rows(*parts: list[dict[str, str]], limit: int = 120) -> list[dict[str, str]]:
    seen: set[str] = set()
    merged: list[dict[str, str]] = []
    for part in parts:
        for row in part:
            key = row.get("job_id") or row.get("job_url")
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(row)
    merged.sort(key=lambda item: int(item.get("match_score") or 0), reverse=True)
    return merged[:limit]


def scrape_from_config(fetcher: ChileTrabajosFetcher | None = None) -> list[dict[str, str]]:
    cfg = load_config()
    ct = chiletrabajos_cfg(cfg)
    parts: list[list[dict[str, str]]] = []
    per_source = max(20, ct["limit"])
    if ct["mode"] in {"both", "rss"}:
        parts.append(
            scrape_rss(
                category_slug=ct["category_slug"],
                min_score=ct["min_score"],
                limit=min(ct["rss_limit"], per_source),
                fetcher=fetcher,
            )
        )
    if ct["mode"] in {"both", "listing"}:
        listing_rows: list[dict[str, str]] = []
        categories = [ct["category_slug"], *ct["extra_categories"]]
        for slug in categories:
            if not slug:
                continue
            per_cat = max(10, per_source // max(1, len(categories)))
            listing_rows.extend(
                scrape_listings(
                    pages=ct["pages"],
                    category_slug=slug,
                    keyword=ct["keyword"],
                    min_score=ct["min_score"],
                    limit=per_cat,
                    fetcher=fetcher,
                )
            )
        parts.append(listing_rows)
    return merge_rows(*parts, limit=ct["limit"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape ChileTrabajos a CSV")
    parser.add_argument("--pages", type=int, default=0, help="Paginas de listado (0=config)")
    parser.add_argument("--category", default="", help="Slug categoria, ej. informatica")
    parser.add_argument("--keyword", default="", help="Palabra clave (filtro final por score)")
    parser.add_argument("--min-score", type=int, default=-1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-session", action="store_true", help="Scrape sin login Playwright (solo HTTP)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ct = chiletrabajos_cfg()
    use_session = ct["use_session"] and not args.no_session and chiletrabajos_session is not None
    try:
        def run_scrape(fetcher: ChileTrabajosFetcher | None = None) -> list[dict[str, str]]:
            if args.pages > 0 or args.category or args.keyword:
                return scrape_listings(
                    pages=args.pages or ct["pages"],
                    category_slug=args.category or ct["category_slug"],
                    keyword=args.keyword or ct["keyword"],
                    min_score=args.min_score if args.min_score >= 0 else ct["min_score"],
                    limit=args.limit or ct["limit"],
                    fetcher=fetcher,
                )
            return scrape_from_config(fetcher=fetcher)

        if use_session:
            with chiletrabajos_session(headless=ct["headless"]) as fetcher:
                rows = run_scrape(fetcher)
        else:
            rows = run_scrape(None)
        path = write_csv(rows, output_csv_path())
        top = rows[0]["title"] if rows else "sin matches"
        payload = {
            "status": "ok",
            "agent": "jobs",
            "source": "chiletrabajos",
            "count": len(rows),
            "csv_file": str(path),
            "latest_csv": str(path.parent / "chiletrabajos_latest.csv"),
            "jobs": rows,
            "whatsapp_reply": f"ChileTrabajos: {len(rows)} vacantes (score>={ct['min_score']}). Top: {top[:70]}. CSV: {path.name}",
        }
    except Exception as exc:
        payload = {
            "status": "error",
            "agent": "jobs",
            "source": "chiletrabajos",
            "count": 0,
            "csv_file": "",
            "latest_csv": str(JOBS_WS / "chiletrabajos_latest.csv"),
            "jobs": [],
            "whatsapp_reply": f"ChileTrabajos fallo: {exc}",
        }
    cache = JOBS_WS / "chiletrabajos_latest.json"
    cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["whatsapp_reply"])
    if payload["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
