"""Respuestas LLM para formularios de postulacion LinkedIn."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any


def answer_field(
    question: str,
    *,
    field_type: str = "text",
    options: list[str] | None = None,
    profile: dict[str, Any],
    cv_excerpt: str,
    vacancy_text: str = "",
) -> str:
    q_low = question.lower()
    defaults = profile.get("profile_answers") or {}

    if any(x in q_low for x in ("autoriz", "eligible", "legally", "work permit", "visa")):
        return defaults.get("work_authorization", "Authorized to work in Chile")
    if any(x in q_low for x in ("year", "año", "anos", "años", "experience")):
        return defaults.get("years_experience", "15+")
    if any(x in q_low for x in ("salary", "sueldo", "compensation", "renta")):
        return defaults.get("salary_expectation", "Market rate for senior role in Chile")
    if any(x in q_low for x in ("notice", "disponibil", "start date", "inicio")):
        return defaults.get("notice_period", "2 weeks")
    if any(x in q_low for x in ("english", "ingles", "inglés")):
        return defaults.get("english_level", "Professional working proficiency")
    if any(x in q_low for x in ("phone", "telefono", "teléfono", "mobile")):
        return profile.get("phone") or defaults.get("phone", "")
    if any(x in q_low for x in ("email", "correo")):
        return profile.get("email") or ""

    if field_type == "select" and options:
        return _pick_option(question, options, profile, cv_excerpt, vacancy_text)

    from intel_localize import litellm_model, litellm_url, master_key

    key = master_key()
    if not key:
        return defaults.get("generic_short", "Yes, I have relevant hands-on experience.")

    system = (
        "Respondes preguntas de formularios de empleo para Mauro Castro "
        "(Senior DevOps/Cloud/SRE, Chile). Respuesta corta, honesta, profesional. "
        "Una oracion o numero cuando aplique. Sin markdown."
    )
    user = (
        f"PREGUNTA: {question}\nTIPO: {field_type}\n"
        f"OPCIONES: {options or []}\n"
        f"VACANTE: {vacancy_text[:800]}\n"
        f"PERFIL: {profile.get('owner')} | {profile.get('location')}\n"
        f"CV: {cv_excerpt[:1200]}"
    )
    payload = {
        "model": litellm_model(),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
        "max_tokens": 120,
    }
    req = urllib.request.Request(
        litellm_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = json.loads(resp.read())["choices"][0]["message"]["content"].strip()
        return re.sub(r"\s+", " ", text)[:500]
    except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError):
        return defaults.get("generic_short", "Yes")


def _pick_option(
    question: str,
    options: list[str],
    profile: dict[str, Any],
    cv_excerpt: str,
    vacancy_text: str,
) -> str:
    ans = answer_field(
        question + " Choose one option exactly from the list.",
        field_type="text",
        options=options,
        profile=profile,
        cv_excerpt=cv_excerpt,
        vacancy_text=vacancy_text,
    )
    low = ans.lower()
    for opt in options:
        if opt.lower() in low or low in opt.lower():
            return opt
    for opt in options:
        if any(tok in opt.lower() for tok in low.split() if len(tok) > 3):
            return opt
    yes_opts = [o for o in options if re.search(r"\byes\b|\bs[ií]\b", o, re.I)]
    if yes_opts and any(x in question.lower() for x in ("do you", "have you", "tienes", "cuentas")):
        return yes_opts[0]
    return options[0]
