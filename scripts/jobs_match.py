#!/usr/bin/env python3
"""Matchea vacantes (LinkedIn + texto pegado) con perfil y CVs de Mauro."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from typing import Any

from jobs_common import (
    CV_INDEX,
    JOBS_WS,
    load_config,
    load_linkedin_job_signals,
    pick_best_cv,
    score_vacancy,
    vacancy_title,
)


def load_cv_index() -> list[dict[str, Any]]:
    if not CV_INDEX.exists():
        return []
    try:
        return list(json.loads(CV_INDEX.read_text(encoding="utf-8")).get("items") or [])
    except json.JSONDecodeError:
        return []


def llm_rank_vacancies(vacancies: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    if not vacancies:
        return []
    from intel_localize import litellm_model, litellm_url, master_key

    key = master_key()
    if not key:
        return vacancies

    brief = [
        {
            "id": i,
            "title": vacancy_title(v.get("text", "")),
            "score": v.get("match_score"),
            "source": v.get("source"),
        }
        for i, v in enumerate(vacancies[:12])
    ]
    payload = {
        "model": litellm_model(),
        "messages": [
            {
                "role": "system",
                "content": "Eres asesor de carrera DevOps/Cloud Chile. JSON solo.",
            },
            {
                "role": "user",
                "content": (
                    f"Perfil: {cfg.get('owner')} — skills {cfg.get('core_skills', [])[:12]}. "
                    f"Ordena por fit real (remoto/LATAM ok). JSON: "
                    '{{"ranked_ids":[...],"notes":{{"0":"motivo corto"}}}} para vacantes:\n'
                    f"{json.dumps(brief, ensure_ascii=False)}"
                ),
            },
        ],
        "temperature": 0,
        "max_tokens": 500,
    }
    req = urllib.request.Request(
        litellm_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = json.loads(resp.read())["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            return vacancies
        parsed = json.loads(m.group(0))
        ranked_ids = parsed.get("ranked_ids") or []
        notes = parsed.get("notes") or {}
        by_id = {i: v for i, v in enumerate(vacancies)}
        out = []
        for rid in ranked_ids:
            if rid in by_id:
                item = dict(by_id[rid])
                item["fit_note"] = notes.get(str(rid)) or notes.get(rid) or ""
                out.append(item)
        for i, v in enumerate(vacancies):
            if i not in ranked_ids:
                out.append(v)
        return out or vacancies
    except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError):
        return vacancies


def build_vacancies_from_text(text: str, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sig in load_linkedin_job_signals(cfg):
        blob = sig.get("text") or ""
        score = score_vacancy(blob, cfg)
        if score < int(cfg.get("min_match_score") or 12):
            continue
        cv = pick_best_cv(blob, load_cv_index())
        out.append({
            "source": "linkedin",
            "keyword": sig.get("keyword"),
            "url": sig.get("url") or "",
            "text": blob,
            "match_score": score,
            "recommended_cv": cv.get("filename") if cv else None,
        })
    if text and len(text) > 40 and not re.search(r"youtube\.com|youtu\.be", text, re.I):
        score = score_vacancy(text, cfg)
        if score >= int(cfg.get("min_match_score") or 12) // 2:
            cv = pick_best_cv(text, load_cv_index())
            out.append({
                "source": "user_text",
                "keyword": None,
                "url": "",
                "text": text,
                "match_score": score,
                "recommended_cv": cv.get("filename") if cv else None,
            })
    out.sort(key=lambda x: x.get("match_score", 0), reverse=True)
    return out


def format_whatsapp(vacancies: list[dict[str, Any]]) -> str:
    if not vacancies:
        return (
            "📋 *Jobs — sin vacantes match hoy*\n\n"
            "No encontré ofertas LinkedIn alineadas en el último scan.\n"
            "Pega la descripción de una vacante o corre scan LinkedIn (`/intel scan linkedin`)."
        )
    lines = [
        f"📋 *Jobs — {len(vacancies)} vacante(s) para tu perfil*",
        "",
    ]
    for i, vac in enumerate(vacancies[:7], 1):
        title = vacancy_title(vac.get("text", ""))
        cv = vac.get("recommended_cv") or "CV general"
        score = vac.get("match_score", 0)
        note = vac.get("fit_note") or ""
        src = vac.get("source", "?")
        lines.append(f"{i}. *{title}*")
        lines.append(f"   Match {score} | CV: `{cv}` | Fuente: {src}")
        if note:
            lines.append(f"   _{note}_")
    lines += [
        "",
        "───",
        "Buscar en LinkedIn Jobs: `/jobs buscar linkedin`",
        "Postular (Easy Apply + CSV): `/jobs postular 1` o `postular auto`",
        "Ver historial: `/jobs mis postulaciones`",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Match vacantes con perfil Mauro")
    parser.add_argument("--text", default="", help="Texto extra o descripcion vacante")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    vacancies = build_vacancies_from_text(args.text, cfg)
    vacancies = llm_rank_vacancies(vacancies, cfg)

    JOBS_WS.mkdir(parents=True, exist_ok=True)
    cache = JOBS_WS / "last_matches.json"
    cache.write_text(json.dumps(vacancies, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    payload = {
        "status": "ok",
        "agent": "jobs",
        "match_count": len(vacancies),
        "matches_file": str(cache),
        "vacancies": vacancies,
        "whatsapp_reply": format_whatsapp(vacancies),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["whatsapp_reply"])


if __name__ == "__main__":
    main()
