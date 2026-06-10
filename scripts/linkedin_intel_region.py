"""Scoring y filtro regional para LinkedIn Intel (default: Chile)."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_REGION = {
    "name": "Chile",
    "geo_urn": "104621616",
    "language": "es",
    "boost_terms": [
        "chile", "chileno", "chilena", "santiago", "stgo", "latam", "latinoamerica",
        "latinoamérica", "concepcion", "concepción", "valparaiso", "valparaíso",
        "region metropolitana", "rm ", " antofagasta", "temuco", "puerto montt",
        "innovacion radical", "innovación radical",
    ],
    "demote_terms": [
        "chicago", "united states", " u.s.", " usa", "new york", "san francisco",
        "texas", "california", "london", " united kingdom", " uk", "hybrid)",
        "remote - us", "estados unidos", "north america",
    ],
    "job_noise_terms": [
        "hiring:", "we're hiring", "we are hiring", "estamos contratando",
        "job opening", "apply now", "📍 location:", "location: chicago",
        "8+ years", "years of experience required",
    ],
}


def region_cfg(config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(DEFAULT_REGION)
    if config:
        cfg.update(config.get("region") or {})
    return cfg


def _terms(text: str) -> str:
    return f" {text.lower()} "


def is_job_noise(text: str, cfg: dict[str, Any] | None = None) -> bool:
    low = _terms(text)
    region = region_cfg(cfg if isinstance(cfg, dict) and "region" in cfg else {"region": cfg})
    return any(t in low for t in region.get("job_noise_terms", []))


def chile_score(text: str, cfg: dict[str, Any] | None = None) -> int:
    region = region_cfg(cfg if isinstance(cfg, dict) and "region" in cfg else {"region": cfg})
    low = _terms(text)
    score = 0
    for term in region.get("boost_terms", []):
        if term in low:
            score += 8
    for term in region.get("demote_terms", []):
        if term in low:
            score -= 12
    if is_job_noise(text, cfg):
        score -= 25
    if re.search(r"\b(espa[nñ]ol|castellano)\b", low):
        score += 3
    return score


def rank_signals(signals: list[dict[str, Any]], cfg: dict[str, Any] | None = None, base_score_fn=None) -> list[dict[str, Any]]:
    def combined(sig: dict[str, Any]) -> int:
        text = sig.get("text") or ""
        base = base_score_fn(text) if base_score_fn else 0
        return base + chile_score(text, cfg)

    ranked = sorted(signals, key=combined, reverse=True)
    return ranked


def pick_top_chile(signals: list[dict[str, Any]], cfg: dict[str, Any] | None = None, limit: int = 6) -> tuple[list[dict[str, Any]], int]:
    ranked = rank_signals(signals, cfg)
    chile_hits = [s for s in ranked if chile_score(s.get("text", ""), cfg) > 0 and not is_job_noise(s.get("text", ""), cfg)]
    if len(chile_hits) >= min(3, limit):
        return chile_hits[:limit], len(chile_hits)
    clean = [s for s in ranked if not is_job_noise(s.get("text", ""), cfg)]
    return (clean or ranked)[:limit], len(chile_hits)
