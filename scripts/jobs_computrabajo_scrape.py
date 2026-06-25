#!/usr/bin/env python3
"""Scrape vacantes desde cl.computrabajo.com a CSV compatible con el pipeline Jobs."""

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

BASE = "https://cl.computrabajo.com"
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

OFFER_BLOCK_RE = re.compile(
    r'<article class="box_offer[^"]*"[^>]*data-id=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</article>',
    re.S | re.I,
)
TITLE_RE = re.compile(r'<a class="js-o-link[^"]*"[^>]*href="([^"]+)"[^>]*>\s*(.*?)\s*</a>', re.S | re.I)
COMPANY_LINK_RE = re.compile(
    r'offer-grid-article-company-url[^>]*>\s*(.*?)\s*</a>',
    re.S | re.I,
)
COMPANY_PLAIN_RE = re.compile(
    r'<p class="dFlex vm_fx fs16 fc_base mt5">\s*(?!.*offer-grid-article-company-url)(.*?)</p>',
    re.S | re.I,
)
LOCATION_RE = re.compile(
    r'<p class="fs16 fc_base mt5">\s*<span class="mr10">\s*(.*?)\s*</span>',
    re.S | re.I,
)
LISTED_RE = re.compile(r'<p class="fs13 fc_aux mt15">\s*(.*?)\s*</p>', re.S | re.I)
JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S | re.I)
DESC_FALLBACK_RE = re.compile(r'<p class="mbB">(.*?)</p>', re.S | re.I)
H1_RE = re.compile(r'<h1[^>]*class="[^"]*box_detail[^"]*"[^>]*>(.*?)</h1>', re.S | re.I)


def job_id_from_url(url: str) -> str:
    match = re.search(r"-([0-9A-F]{20,})(?:#|\?|$)", url.rstrip("/"), re.I)
    return match.group(1).upper() if match else ""


def clean_text(raw: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    return re.sub(r"\s+", " ", text).strip()


def infer_workplace(location: str, summary: str) -> str:
    blob = f"{location} {summary}".lower()
    if "teletrabajo" in blob or "remoto" in blob or "remote" in blob:
        return "remote"
    if "hibrido" in blob or "híbrido" in blob or "hybrid" in blob:
        return "hybrid"
    if "presencial" in blob or "on-site" in blob or "onsite" in blob or "en sitio" in blob:
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


def listing_url(category_slug: str, region_suffix: str = "") -> str:
    slug = category_slug.strip("/")
    if region_suffix:
        slug = f"{slug}-{region_suffix.strip('/')}"
    return urljoin(BASE, f"/trabajo-de-{slug}")


def parse_listing_page(page_html: str, scraped_at: str, collection_url: str, cfg: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for job_id, body in OFFER_BLOCK_RE.findall(page_html):
        title_match = TITLE_RE.search(body)
        if not title_match:
            continue
        href, title_raw = title_match.group(1), title_match.group(2)
        job_url = urljoin(BASE, href.split("#")[0])
        title = clean_text(title_raw)
        company_match = COMPANY_LINK_RE.search(body)
        if company_match:
            company = clean_text(company_match.group(1))
        else:
            company_plain = COMPANY_PLAIN_RE.search(body)
            company = clean_text(company_plain.group(1)) if company_plain else ""
        location_match = LOCATION_RE.search(body)
        location = clean_text(location_match.group(1)) if location_match else ""
        listed_match = LISTED_RE.search(body)
        listed_at = clean_text(listed_match.group(1)) if listed_match else ""
        promoted = "1" if "outstanding" in body[:120].lower() or "destacado" in body.lower() else "0"
        summary = title
        text = " ".join(x for x in (title, company, location, summary) if x)
        rows.append(
            {
                "scraped_at": scraped_at,
                "source": "computrabajo",
                "job_id": job_id_from_url(job_url) or job_id.upper(),
                "title": title[:200],
                "company": company[:160],
                "location": location[:160],
                "workplace": infer_workplace(location, summary),
                "listed_at": listed_at[:80],
                "easy_apply": "0",
                "promoted": promoted,
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
    if posting:
        desc_raw = str(posting.get("description") or "")
        desc = clean_text(re.sub(r"<br\s*/?>", "\n", desc_raw, flags=re.I))
        org = posting.get("hiringOrganization") or {}
        address = (posting.get("jobLocation") or {}).get("address") or {}
        location = ", ".join(
            x
            for x in (
                address.get("addressRegion"),
                address.get("addressLocality"),
                address.get("addressCountry"),
            )
            if x
        )
        return {
            "title": clean_text(str(posting.get("title") or ""))[:200],
            "company": clean_text(str(org.get("name") or ""))[:160],
            "location": location[:160],
            "description": desc,
            "listed_at": str(posting.get("datePosted") or "")[:80],
            "category": str(posting.get("industry") or "")[:120],
            "job_type": str(posting.get("employmentType") or "")[:80],
            "workplace": infer_workplace(location, desc),
        }

    h1_match = H1_RE.search(page)
    title = clean_text(h1_match.group(1)) if h1_match else ""
    desc_match = DESC_FALLBACK_RE.search(page)
    desc = clean_text(desc_match.group(1)) if desc_match else ""
    return {
        "title": title[:200],
        "company": "",
        "location": "",
        "description": desc,
        "listed_at": "",
        "category": "",
        "job_type": "",
        "workplace": infer_workplace("", desc),
    }


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


def computrabajo_cfg(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    raw = cfg.get("computrabajo") or {}
    categories = list(raw.get("categories") or ["informatica", "devops", "cloud", "devsecops", "mlops"])
    return {
        "categories": [str(x).strip("/") for x in categories if str(x).strip()],
        "region_suffix": str(raw.get("region_suffix") or "en-rmetropolitana"),
        "min_score": int(raw.get("min_score") or cfg.get("min_match_score") or 12),
        "limit": int(raw.get("limit") or 80),
    }


def scrape_from_config() -> list[dict[str, str]]:
    cfg = load_config()
    ct = computrabajo_cfg(cfg)
    scraped_at = datetime.now().astimezone().isoformat(timespec="seconds")
    parts: list[list[dict[str, str]]] = []
    per_source = max(10, ct["limit"] // max(1, len(ct["categories"])))
    for category in ct["categories"]:
        url = listing_url(category, ct["region_suffix"])
        try:
            page_html = fetch_html(url)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"No se pudo leer {url}: {exc}") from exc
        batch = parse_listing_page(page_html, scraped_at, url, cfg)
        batch.sort(key=lambda item: int(item.get("match_score") or 0), reverse=True)
        filtered = [row for row in batch if int(row.get("match_score") or 0) >= ct["min_score"]]
        parts.append(filtered[:per_source])
    merged = merge_rows(*parts, limit=ct["limit"])
    return merged


def output_csv_path(run_date: str | None = None) -> Path:
    run_date = run_date or datetime.now().strftime("%Y-%m-%d")
    return JOBS_WS / f"computrabajo_{run_date}.csv"


def write_csv(rows: list[dict[str, str]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    latest = path.parent / "computrabajo_latest.csv"
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Computrabajo Chile a CSV")
    parser.add_argument("--category", default="", help="Slug categoria, ej. informatica")
    parser.add_argument("--region", default="", help="Sufijo region, ej. en-rmetropolitana")
    parser.add_argument("--min-score", type=int, default=-1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ct = computrabajo_cfg()
    try:
        if args.category:
            url = listing_url(args.category, args.region or ct["region_suffix"])
            scraped_at = datetime.now().astimezone().isoformat(timespec="seconds")
            page_html = fetch_html(url)
            rows = parse_listing_page(page_html, scraped_at, url, load_config())
            min_score = args.min_score if args.min_score >= 0 else ct["min_score"]
            limit = args.limit or ct["limit"]
            rows = [row for row in rows if int(row.get("match_score") or 0) >= min_score]
            rows.sort(key=lambda item: int(item.get("match_score") or 0), reverse=True)
            rows = rows[:limit]
        else:
            rows = scrape_from_config()
        path = write_csv(rows, output_csv_path())
        top = rows[0]["title"] if rows else "sin matches"
        payload = {
            "status": "ok",
            "agent": "jobs",
            "source": "computrabajo",
            "count": len(rows),
            "csv_file": str(path),
            "latest_csv": str(path.parent / "computrabajo_latest.csv"),
            "jobs": rows,
            "whatsapp_reply": (
                f"Computrabajo: {len(rows)} vacantes (score>={ct['min_score']}). "
                f"Top: {top[:70]}. CSV: {path.name}"
            ),
        }
    except Exception as exc:
        payload = {
            "status": "error",
            "agent": "jobs",
            "source": "computrabajo",
            "count": 0,
            "csv_file": "",
            "latest_csv": str(JOBS_WS / "computrabajo_latest.csv"),
            "jobs": [],
            "whatsapp_reply": f"Computrabajo fallo: {exc}",
        }
    cache = JOBS_WS / "computrabajo_latest.json"
    cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["whatsapp_reply"])
    if payload["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
