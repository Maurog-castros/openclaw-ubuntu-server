"""GitHub repository trend/search report for OpenClaw."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any, Dict, List

SORT_MAP = {
    "stars": "stars",
    "estrellas": "stars",
    "forks": "forks",
    "updated": "updated",
    "actualizados": "updated",
}


def build_query(args: argparse.Namespace) -> str:
    parts: List[str] = []
    if args.query:
        parts.append(args.query)
    if args.language:
        parts.append(f"language:{args.language}")
    if args.created_after:
        parts.append(f"created:>={args.created_after}")
    if args.pushed_after:
        parts.append(f"pushed:>={args.pushed_after}")
    if args.min_stars:
        parts.append(f"stars:>={args.min_stars}")
    if not parts:
        # Good default: recently active popular repos, broad enough for trend scan.
        pushed = (date.today() - timedelta(days=30)).isoformat()
        parts.append(f"pushed:>={pushed}")
        parts.append("stars:>=1000")
    return " ".join(parts)


def github_search(query: str, sort: str, limit: int) -> Dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "sort": sort,
            "order": "desc",
            "per_page": max(1, min(limit, 20)),
        }
    )
    req = urllib.request.Request(
        f"https://api.github.com/search/repositories?{params}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "openclaw-mauro-github-trends",
        },
    )
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
        payload["rate_limit_remaining"] = response.headers.get("x-ratelimit-remaining")
        payload["rate_limit_reset"] = response.headers.get("x-ratelimit-reset")
        return payload


def summarize(items: List[Dict[str, Any]], query: str, sort: str) -> str:
    label = "estrellas" if sort == "stars" else "forks" if sort == "forks" else "actividad"
    lines = [f"GitHub repos por {label}", f"Filtro: {query}"]
    if not items:
        lines.append("Sin resultados.")
        return "\n".join(lines)
    for idx, repo in enumerate(items, start=1):
        desc = (repo.get("description") or "").strip().replace("\n", " ")[:100]
        lang = repo.get("language") or "n/a"
        stars = int(repo.get("stargazers_count") or 0)
        forks = int(repo.get("forks_count") or 0)
        pushed = (repo.get("pushed_at") or "")[:10]
        lines.append(
            f"{idx}. {repo.get('full_name')} | ⭐ {stars:,} | forks {forks:,} | {lang} | upd {pushed}".replace(",", ".")
        )
        if desc:
            lines.append(f"   {desc}")
        lines.append(f"   {repo.get('html_url')}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tendencias GitHub repos por estrellas/forks/actividad.")
    parser.add_argument("--query", default="", help="Query GitHub search adicional, ej. ai agent")
    parser.add_argument("--language", default="")
    parser.add_argument("--sort", default="stars", choices=sorted(SORT_MAP))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--created-after", default="")
    parser.add_argument("--pushed-after", default="")
    parser.add_argument("--min-stars", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    sort = SORT_MAP[args.sort]
    query = build_query(args)
    try:
        payload = github_search(query, sort, args.limit)
    except Exception as exc:
        result = {"status": "error", "message": f"GitHub search fallo: {exc}"}
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["message"])
        raise SystemExit(1)

    items = payload.get("items") or []
    repos = [
        {
            "full_name": item.get("full_name"),
            "url": item.get("html_url"),
            "description": item.get("description") or "",
            "language": item.get("language") or "",
            "stars": item.get("stargazers_count") or 0,
            "forks": item.get("forks_count") or 0,
            "open_issues": item.get("open_issues_count") or 0,
            "created_at": item.get("created_at"),
            "pushed_at": item.get("pushed_at"),
        }
        for item in items
    ]
    summary = summarize(items, query, sort)
    result = {
        "status": "ok",
        "query": query,
        "sort": sort,
        "count": len(repos),
        "rate_limit_remaining": payload.get("rate_limit_remaining"),
        "repos": repos,
        "summary": summary,
        "whatsapp_reply": summary,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else summary)


if __name__ == "__main__":
    main()
