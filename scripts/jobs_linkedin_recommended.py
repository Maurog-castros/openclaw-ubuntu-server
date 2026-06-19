#!/usr/bin/env python3
"""Exporta LinkedIn Jobs recomendados a CSV."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from jobs_common import JOBS_WS, load_config, score_vacancy
from jobs_linkedin_browser import ensure_login, launch_browser, new_context

RECOMMENDED_URL = "https://www.linkedin.com/jobs/collections/recommended/"

CSV_COLUMNS = [
    "scraped_at",
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

JS_EXTRACT_RECOMMENDED = """
() => {
  const cards = Array.from(document.querySelectorAll(
    'li.jobs-search-results__list-item, div.job-card-container, div[data-job-id], a[href*="/jobs/view/"]'
  ));
  const out = [];
  const seen = new Set();
  for (const el of cards) {
    let link = el.querySelector('a[href*="/jobs/view/"]');
    if (!link && el.matches('a[href*="/jobs/view/"]')) link = el;
    if (!link) continue;
    const href = link.href || '';
    const canonical = href.split('?')[0];
    if (!canonical || seen.has(canonical)) continue;
    seen.add(canonical);
    const text = (el.innerText || '').replace(/\\s+/g, ' ').trim();
    const titleEl = el.querySelector(
      '.job-card-list__title, .job-card-container__link, .artdeco-entity-lockup__title, strong, h3'
    );
    const companyEl = el.querySelector(
      '.job-card-container__company-name, .artdeco-entity-lockup__subtitle, .job-card-container__primary-description'
    );
    const locationEl = el.querySelector(
      '.job-card-container__metadata-item, .artdeco-entity-lockup__caption'
    );
    out.push({
      title: (titleEl?.innerText || link.innerText || '').replace(/\\s+/g, ' ').trim(),
      company: (companyEl?.innerText || '').replace(/\\s+/g, ' ').trim(),
      location: (locationEl?.innerText || '').replace(/\\s+/g, ' ').trim(),
      job_url: canonical,
      collection_url: href,
      easy_apply: /Solicitud sencilla|Easy Apply/i.test(text),
      promoted: /Promocionado|Promoted/i.test(text),
      listed_at: ((text.match(/(Hace [^·]+|\\d+\\s+(?:h|d|sem|mes)|Reposted|Publicado[^·]*)/i) || [])[0] || ''),
      summary: text.slice(0, 500),
    });
  }
  return out;
}
"""


def job_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if qs.get("currentJobId"):
        return qs["currentJobId"][0]
    match = re.search(r"/jobs/view/(\d+)", parsed.path)
    return match.group(1) if match else ""


def output_csv_path(run_date: str | None = None) -> Path:
    run_date = run_date or datetime.now().strftime("%Y-%m-%d")
    return JOBS_WS / f"linkedin_recommended_{run_date}.csv"


def normalize_rows(raw: list[dict[str, Any]], scraped_at: str, cfg: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        job_url = str(item.get("job_url") or "").split("?")[0].rstrip("/")
        collection_url = str(item.get("collection_url") or "")
        job_id = job_id_from_url(collection_url) or job_id_from_url(job_url)
        key = job_id or job_url
        if not key or key in seen:
            continue
        seen.add(key)
        text = " ".join(str(item.get(k) or "") for k in ("title", "company", "location", "summary"))
        location = str(item.get("location") or "")
        rows.append(
            {
                "scraped_at": scraped_at,
                "job_id": job_id,
                "title": str(item.get("title") or "")[:200],
                "company": str(item.get("company") or "")[:160],
                "location": location[:160],
                "workplace": infer_workplace(location, str(item.get("summary") or "")),
                "listed_at": str(item.get("listed_at") or "")[:80],
                "easy_apply": "1" if item.get("easy_apply") else "0",
                "promoted": "1" if item.get("promoted") else "0",
                "match_score": str(score_vacancy(text, cfg)),
                "job_url": job_url,
                "collection_url": collection_url,
                "summary": str(item.get("summary") or "")[:500],
            }
        )
    return rows


def infer_workplace(location: str, summary: str) -> str:
    blob = f"{location} {summary}".lower()
    if "remoto" in blob or "remote" in blob:
        return "remote"
    if "hibrido" in blob or "híbrido" in blob or "hybrid" in blob:
        return "hybrid"
    if "presencial" in blob or "on-site" in blob or "onsite" in blob:
        return "onsite"
    return ""


def write_csv(rows: list[dict[str, str]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    latest = path.parent / "linkedin_recommended_latest.csv"
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def scrape_recommended(*, limit: int = 80, headless: bool = True) -> list[dict[str, str]]:
    from playwright.sync_api import sync_playwright

    cfg = load_config()
    scraped_at = datetime.now().astimezone().isoformat(timespec="seconds")
    with sync_playwright() as p:
        browser = launch_browser(p, headless=headless)
        context = new_context(browser, cfg)
        page = context.new_page()
        try:
            ensure_login(page, cfg)
            page.goto(RECOMMENDED_URL, wait_until="domcontentloaded", timeout=90000)
            time.sleep(4)
            for _ in range(8):
                page.mouse.wheel(0, 2400)
                time.sleep(1)
            raw = page.evaluate(JS_EXTRACT_RECOMMENDED)
        finally:
            context.close()
            browser.close()
    return normalize_rows(list(raw)[:limit], scraped_at, cfg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Exportar LinkedIn Jobs recomendados a CSV")
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        rows = scrape_recommended(limit=args.limit, headless=not args.headed)
        path = write_csv(rows, output_csv_path())
        payload = {
            "status": "ok",
            "agent": "jobs",
            "count": len(rows),
            "csv_file": str(path),
            "latest_csv": str(path.parent / "linkedin_recommended_latest.csv"),
            "jobs": rows,
            "whatsapp_reply": f"LinkedIn recommended: {len(rows)} vacantes exportadas a {path}",
        }
    except Exception as exc:
        payload = {
            "status": "error",
            "agent": "jobs",
            "count": 0,
            "csv_file": "",
            "latest_csv": str(JOBS_WS / "linkedin_recommended_latest.csv"),
            "jobs": [],
            "whatsapp_reply": f"LinkedIn recommended fallo: {exc}",
        }
    cache = JOBS_WS / "linkedin_recommended_latest.json"
    cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["whatsapp_reply"])
    if payload["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
