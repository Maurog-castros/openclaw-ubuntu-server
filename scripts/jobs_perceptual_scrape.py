#!/usr/bin/env python3
"""Scrape vacantes desde laboral.perceptual.cl a CSV compatible con el pipeline Jobs."""

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
from urllib.parse import urljoin

from jobs_common import JOBS_WS, load_config, score_vacancy

BASE = "https://laboral.perceptual.cl"
LISTING_URL = f"{BASE}/empleos/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

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

LISTING_ITEM_RE = re.compile(
    r'id="awsm-list-item-(\d+)"[^>]*>(.*?)(?=id="awsm-list-item-|<div class="awsm-load-more-main"|$)',
    re.S | re.I,
)
TITLE_RE = re.compile(
    r'<h2 class="awsm-job-post-title">\s*<a href="([^"]+)"[^>]*>(.*?)</a>\s*</h2>',
    re.S | re.I,
)
INTRO_RE = re.compile(r'<div class="z-intro">\s*<p>(.*?)</p>\s*</div>', re.S | re.I)
DATE_RE = re.compile(r'<div class="z-publish-date">\s*(?:Publicado:\s*)?([^<]+)</div>', re.S | re.I)
SPEC_TERM_RE = re.compile(
    r'awsm-job-specification-job-(\w+)[^>]*>\s*<span class="awsm-job-specification-term">([^<]+)</span>',
    re.S | re.I,
)
JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S | re.I)
CONTENT_SINGLE_RE = re.compile(
    r'<div class="z-content-single">(.*?)</div>\s*(?:<div class="z-|</div>\s*</div>\s*</div>\s*<footer)',
    re.S | re.I,
)
FEATURES_RE = re.compile(r'<div class="z-features">(.*?)</div>', re.S | re.I)
CODE_RE = re.compile(r'<span class="codigo">.*?(\d{5,})</span>', re.S | re.I)
H1_RE = re.compile(r'<h1[^>]*class="[^"]*awsm-jobs-single-title[^"]*"[^>]*>(.*?)</h1>', re.S | re.I)


def clean_text(raw: str) -> str:
    text = html.unescape(re.sub(r"<br\s*/?>", "\n", raw or "", flags=re.I))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_description(raw: str) -> str:
    text = html.unescape(re.sub(r"<br\s*/?>", "\n", raw or "", flags=re.I))
    text = re.sub(r"</p>\s*<p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def infer_workplace(location: str, summary: str, modality: str = "") -> str:
    blob = f"{location} {summary} {modality}".lower()
    if any(x in blob for x in ("remoto", "remote", "home office", "homeoffice", "teletrabajo", "telemático")):
        return "remote"
    if any(x in blob for x in ("hibrid", "híbrid", "hybrid", "mixta")):
        return "hybrid"
    if any(x in blob for x in ("presencial", "on-site", "onsite", "terreno")):
        return "onsite"
    return ""


def fetch_html(url: str, timeout: int = 45) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "es-CL,es;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_listing_page(page_html: str, scraped_at: str, collection_url: str, cfg: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for job_id, body in LISTING_ITEM_RE.findall(page_html):
        title_match = TITLE_RE.search(body)
        if not title_match:
            continue
        href, title_raw = title_match.group(1), title_match.group(2)
        job_url = urljoin(BASE, href.split("#")[0])
        title = clean_text(title_raw)
        intro_match = INTRO_RE.search(body)
        intro = clean_text(intro_match.group(1)) if intro_match else ""
        date_match = DATE_RE.search(body)
        listed_at = clean_text(date_match.group(1)) if date_match else ""
        specs = {name.lower(): clean_text(value) for name, value in SPEC_TERM_RE.findall(body)}
        location = specs.get("location", "")
        modality = specs.get("type", "")
        category = specs.get("category", "")
        summary = " — ".join(x for x in (intro, category) if x) or title
        text = " ".join(x for x in (title, intro, location, modality, category) if x)
        rows.append(
            {
                "scraped_at": scraped_at,
                "source": "perceptual",
                "job_id": job_id,
                "title": title[:200],
                "company": "Perceptual Consultores",
                "location": location[:160],
                "workplace": infer_workplace(location, intro, modality),
                "listed_at": listed_at[:80],
                "easy_apply": "0",
                "promoted": "0",
                "match_score": str(score_vacancy(text, cfg)),
                "job_url": job_url,
                "collection_url": collection_url,
                "summary": summary[:500],
            }
        )
    return rows


def _job_posting_from_json_ld(page: str) -> dict[str, Any] | None:
    for match in JSON_LD_RE.finditer(page):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        graphs = payload.get("@graph") if isinstance(payload, dict) else None
        items = graphs if isinstance(graphs, list) else [payload]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return None


def fetch_job_detail(job_url: str) -> dict[str, str]:
    page = fetch_html(job_url)
    posting = _job_posting_from_json_ld(page)
    code_match = CODE_RE.search(page)
    job_code = code_match.group(1) if code_match else ""

    content_match = CONTENT_SINGLE_RE.search(page)
    features_match = FEATURES_RE.search(page)
    description_parts: list[str] = []
    if content_match:
        description_parts.append(clean_description(content_match.group(1)))
    if features_match:
        description_parts.append(clean_description(features_match.group(1)))
    description = "\n\n".join(part for part in description_parts if part).strip()

    h1_match = H1_RE.search(page)
    title = clean_text(h1_match.group(1)) if h1_match else ""
    location = ""
    modality = ""
    category = ""
    listed_at = ""

    if posting:
        title = title or clean_text(str(posting.get("title") or ""))
        listed_at = str(posting.get("datePosted") or "")[:80]
        job_location = posting.get("jobLocation") or {}
        if isinstance(job_location, list):
            job_location = job_location[0] if job_location else {}
        address = job_location.get("address") if isinstance(job_location, dict) else {}
        if isinstance(address, str):
            location = clean_text(address)
        elif isinstance(address, dict):
            location = ", ".join(
                x
                for x in (
                    address.get("addressLocality"),
                    address.get("addressRegion"),
                    address.get("addressCountry"),
                )
                if x
            )
        json_desc = clean_text(str(posting.get("description") or ""))
        if len(json_desc) > len(description):
            description = json_desc

    for name, value in re.findall(
        r'awsm-job-specification-job-(\w+)[^>]*>.*?class="awsm-job-specification-term">([^<]+)</a>',
        page,
        re.S | re.I,
    ):
        key = name.lower()
        if key == "location" and not location:
            location = clean_text(value)
        elif key == "type" and not modality:
            modality = clean_text(value)
        elif key == "category" and not category:
            category = clean_text(value)

    intro_match = INTRO_RE.search(page)
    if intro_match and len(description) < 120:
        description = clean_text(intro_match.group(1))

    return {
        "title": title[:200],
        "company": "Perceptual Consultores",
        "location": location[:160],
        "description": description,
        "listed_at": listed_at[:80],
        "category": category[:120],
        "job_type": modality[:80],
        "workplace": infer_workplace(location, description, modality),
        "job_code": job_code,
    }


def perceptual_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    raw = cfg.get("perceptual") or {}
    return {
        "listing_url": str(raw.get("listing_url") or LISTING_URL),
        "min_score": int(raw.get("min_score") or cfg.get("min_match_score") or 12),
        "limit": int(raw.get("limit") or 80),
    }


def scrape_from_config() -> list[dict[str, str]]:
    cfg = load_config()
    portal = perceptual_cfg(cfg)
    scraped_at = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        page_html = fetch_html(portal["listing_url"])
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"No se pudo leer {portal['listing_url']}: {exc}") from exc
    rows = parse_listing_page(page_html, scraped_at, portal["listing_url"], cfg)
    rows = [row for row in rows if int(row.get("match_score") or 0) >= portal["min_score"]]
    rows.sort(key=lambda item: int(item.get("match_score") or 0), reverse=True)
    return rows[: portal["limit"]]


def output_csv_path(run_date: str | None = None) -> Path:
    run_date = run_date or datetime.now().strftime("%Y-%m-%d")
    return JOBS_WS / f"perceptual_{run_date}.csv"


def write_csv(rows: list[dict[str, str]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    latest = path.parent / "perceptual_latest.csv"
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Perceptual laboral a CSV")
    parser.add_argument("--min-score", type=int, default=-1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    portal = perceptual_cfg()
    try:
        rows = scrape_from_config()
        min_score = args.min_score if args.min_score >= 0 else portal["min_score"]
        limit = args.limit or portal["limit"]
        rows = [row for row in rows if int(row.get("match_score") or 0) >= min_score][:limit]
        path = write_csv(rows, output_csv_path())
        top = rows[0]["title"] if rows else "sin matches"
        payload = {
            "status": "ok",
            "agent": "jobs",
            "source": "perceptual",
            "count": len(rows),
            "csv_file": str(path),
            "latest_csv": str(path.parent / "perceptual_latest.csv"),
            "jobs": rows,
            "whatsapp_reply": (
                f"Perceptual: {len(rows)} vacantes (score>={min_score}). "
                f"Top: {top[:70]}. CSV: {path.name}"
            ),
        }
    except Exception as exc:
        payload = {
            "status": "error",
            "agent": "jobs",
            "source": "perceptual",
            "count": 0,
            "csv_file": "",
            "latest_csv": str(JOBS_WS / "perceptual_latest.csv"),
            "jobs": [],
            "whatsapp_reply": f"Perceptual fallo: {exc}",
        }
    cache = JOBS_WS / "perceptual_latest.json"
    cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["whatsapp_reply"])
    if payload["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
