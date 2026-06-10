#!/usr/bin/env python3
"""Busca vacantes LinkedIn Jobs (Easy Apply) con Playwright."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from jobs_common import JOBS_WS, load_config, pick_best_cv, score_vacancy
from jobs_linkedin_browser import (
    build_jobs_search_url,
    ensure_login,
    JS_EXTRACT_JOBS,
    launch_browser,
    new_context,
)
from jobs_match import load_cv_index


def search_jobs(keywords: str, *, limit: int = 15, headless: bool = True) -> list[dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    cfg = load_config()
    cv_index = load_cv_index()
    results: list[dict[str, Any]] = []

    with sync_playwright() as p:
        browser = launch_browser(p, headless=headless)
        context = new_context(browser, cfg)
        page = context.new_page()
        try:
            ensure_login(page, cfg)
            page.goto(build_jobs_search_url(keywords, cfg), wait_until="domcontentloaded", timeout=90000)
            time.sleep(4)
            for _ in range(3):
                page.mouse.wheel(0, 2400)
                time.sleep(1.5)
            raw = page.evaluate(JS_EXTRACT_JOBS)
            for item in raw:
                text = f"{item.get('title')} {item.get('company')}"
                score = score_vacancy(text, cfg)
                if score < int(cfg.get("min_match_score") or 12):
                    continue
                cv = pick_best_cv(text, cv_index)
                results.append({
                    "source": "linkedin_jobs",
                    "title": item.get("title"),
                    "company": item.get("company"),
                    "job_url": item.get("job_url"),
                    "url": item.get("job_url"),
                    "text": f"{item.get('title')} — {item.get('company')}",
                    "easy_apply": item.get("easy_apply", True),
                    "match_score": score,
                    "recommended_cv": cv.get("filename") if cv else None,
                    "keyword": keywords,
                })
                if len(results) >= limit:
                    break
        finally:
            context.close()
            browser.close()

    results.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Buscar vacantes LinkedIn Jobs")
    parser.add_argument("--keywords", default="")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    kws = args.keywords or " ".join((cfg.get("job_search_keywords") or ["devops engineer"])[:2])
    jobs = search_jobs(kws, limit=args.limit, headless=not args.headed)

    JOBS_WS.mkdir(parents=True, exist_ok=True)
    cache = JOBS_WS / "last_matches.json"
    cache.write_text(json.dumps(jobs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [f"🔎 *Jobs — {len(jobs)} vacante(s) LinkedIn (Easy Apply)*", ""]
    for i, job in enumerate(jobs[:8], 1):
        lines.append(f"{i}. *{job.get('title')}* @ {job.get('company')}")
        lines.append(f"   Score {job.get('match_score')} | CV: `{job.get('recommended_cv')}`")
        lines.append(f"   {job.get('job_url')}")
    lines.append("\nPostular: `/jobs postular 1` o `/jobs postular auto`")

    payload = {
        "status": "ok",
        "agent": "jobs",
        "count": len(jobs),
        "matches_file": str(cache),
        "vacancies": jobs,
        "whatsapp_reply": "\n".join(lines) if jobs else "Sin vacantes LinkedIn Jobs con match.",
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["whatsapp_reply"])


if __name__ == "__main__":
    main()
