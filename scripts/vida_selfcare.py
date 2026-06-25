"""Self-care guardrails and structured memory for Fede."""
from __future__ import annotations

import argparse
import json
import re
from typing import Any

from vida_common import care_data, now_local, reply, truncate_whatsapp

PROFILE_FILE = "selfcare_profile.json"
LOG_FILE = "selfcare_log.jsonl"

TINNITUS_RE = re.compile(r"\b(tinnitus|pitido|zumbido|o[ií]do|oifo)\b", re.I)
SUPPLEMENT_RE = re.compile(r"\b(suplement|melena\s+de\s+le[oó]n|b12|creatina)\b", re.I)
SLEEP_RE = re.compile(r"\b(dormir|sue[ñn]o|insomnio|despert[eé]|almohad|cama)\b", re.I)
CRISIS_RE = re.compile(
    r"\b(no\s+puedo\s+m[aá]s|me\s+quiero\s+morir|suicid|hacerme\s+da[ñn]o|"
    r"no\s+quiero\s+vivir|terminar\s+con\s+todo)\b",
    re.I,
)
RED_FLAG_RE = re.compile(
    r"\b(p[eé]rdida\s+s[uú]bita\s+de\s+audici[oó]n|mareo\s+severo|dolor\s+fuerte|"
    r"s[ií]ntomas?\s+neurol[oó]gic|empeoramiento\s+brusco)\b",
    re.I,
)
MICRO_WIN_RE = re.compile(
    r"\b(camin[eé]|caminar|entrevista|estudi[eé]|avanc[eé]|termin[eé]|cocin[eé]|"
    r"buen\s+[aá]nimo|dorm[ií]\s+mejor|me\s+levant[eé]|desayun[eé])\b",
    re.I,
)
HEALTH_DATA_RE = re.compile(
    r"\b("
    r"datos\s+de\s+salud|"
    r"ultim(?:os|as)\s+(?:datos|registros?).*salud|"
    r"qu[eé]\s+registr(?:aste|ó)|"
    r"registr(?:aste|ó)\s+(?:de\s+)?(?:salud|autocuidado)|"
    r"ultimo\s+registro\s+de\s+salud"
    r")\b",
    re.I,
)
REPETITIVE_FEEDBACK_RE = re.compile(
    r"\b(mismo\s+consejo|siempre\s+(?:me\s+)?(?:das|dices)\s+(?:lo\s+mismo|el\s+mismo|ese\s+mismo))\b",
    re.I,
)


DEFAULT_PROFILE: dict[str, Any] = {
    "sleep": {
        "preferred_position": "fetal con almohada entre piernas y otra abrazada",
        "main_blocker": "tinnitus oído izquierdo",
        "routine_exists": False,
    },
    "health": {
        "tinnitus": {
            "side": "left",
            "duration_months": 6,
            "status": "waiting_exam_results",
            "red_flags_checked": False,
        }
    },
    "supplements": [
        {"name": "melena de león", "type": "supplement", "started_approx": "2026-05"},
        {"name": "B12 complex", "type": "supplement", "started_approx": "2026-05"},
        {"name": "creatina", "type": "supplement", "started_approx": "2026-05"},
    ],
    "morning_pattern": {"wakes_hungry": True},
}


def profile_path():
    return care_data() / PROFILE_FILE


def load_profile() -> dict[str, Any]:
    path = profile_path()
    if not path.exists():
        save_profile(DEFAULT_PROFILE)
        return json.loads(json.dumps(DEFAULT_PROFILE, ensure_ascii=False))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
    merged = json.loads(json.dumps(DEFAULT_PROFILE, ensure_ascii=False))
    merged.update(data)
    return merged


def save_profile(data: dict[str, Any]) -> None:
    path = profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_log(intent: str, text: str, *, risk: str = "none") -> None:
    path = care_data() / LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "at": now_local().isoformat(),
        "intent": intent,
        "risk": risk,
        "metrics": {
            "sleep_latency_minutes": None,
            "wake_time": None,
            "tinnitus_intensity_0_10": None,
            "mood_0_10": None,
            "energy_0_10": None,
            "supplements_taken": None,
            "night_routine_completed": None,
            "red_flags_detected": risk != "none",
        },
        "text_preview": truncate_whatsapp(text, max_len=160),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def care_context_dir() -> Path:
    return care_data().parent / "context"


def read_log_tail(limit: int = 3) -> list[dict[str, Any]]:
    path = care_data() / LOG_FILE
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def handle_repetitive_feedback(text: str) -> dict[str, Any] | None:
    if not REPETITIVE_FEEDBACK_RE.search(text):
        return None
    return reply(
        "Fede: tienes razón, suena repetido. Cambio el enfoque: dime qué parte te cansó "
        "(ánimo, sueño, tinnitus, rutina) y te propongo una acción distinta de 2-10 min. "
        "¿Ánimo 0-10 ahora?"
    )


def handle_health_data_query(text: str) -> dict[str, Any] | None:
    if not HEALTH_DATA_RE.search(text):
        return None

    lines = ["Fede: últimos datos de salud que tengo registrados:"]
    logs = read_log_tail(3)
    if logs:
        for item in reversed(logs):
            day = str(item.get("at") or "")[:10] or "?"
            intent = item.get("intent") or "nota"
            preview = str(item.get("text_preview") or "").strip()
            lines.append(f"• {day} ({intent}): {preview or '(sin texto)'}")
    else:
        lines.append("• Aún no hay entradas en selfcare_log.")

    profile = load_profile()
    tinnitus = (profile.get("health") or {}).get("tinnitus") or {}
    if tinnitus:
        side = tinnitus.get("side") or "?"
        months = tinnitus.get("duration_months")
        status = tinnitus.get("status") or ""
        lines.append(
            f"• Perfil tinnitus: lado {side}"
            + (f", ~{months} meses" if months else "")
            + (f", estado {status}" if status else "")
            + "."
        )

    supplements = profile.get("supplements") or []
    if supplements:
        names = ", ".join(str(s.get("name") or "?") for s in supplements[:4])
        lines.append(f"• Suplementos en perfil: {names}.")

    coverage_path = care_context_dir() / "health_coverage.json"
    if coverage_path.exists():
        try:
            coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
            summary = str(coverage.get("freshness_summary") or "").strip()
            metric_day = str(coverage.get("last_metric_date") or "").strip()
            if summary:
                lines.append(f"• Apple Health: {summary}")
            elif metric_day:
                lines.append(f"• Apple Health: métricas hasta {metric_day}.")
        except json.JSONDecodeError:
            pass

    health_today = care_context_dir() / "health_today.md"
    if health_today.exists():
        head = health_today.read_text(encoding="utf-8").splitlines()[:8]
        title = next((ln.strip("# ").strip() for ln in head if ln.startswith("# Health")), "")
        if title:
            lines.append(f"• Reporte: {title}.")

    lines.append("Si falta algo, dime qué registrar (sueño, ánimo, tinnitus 0-10).")
    return reply(truncate_whatsapp("\n".join(lines), max_len=500))


def detect_intent(text: str) -> str | None:
    if CRISIS_RE.search(text):
        return "crisis"
    if RED_FLAG_RE.search(text):
        return "red_flag"
    if TINNITUS_RE.search(text):
        return "tinnitus"
    if SUPPLEMENT_RE.search(text):
        return "supplements"
    if SLEEP_RE.search(text):
        return "sleep"
    if MICRO_WIN_RE.search(text):
        return "micro_win"
    return None


def handle(text: str) -> dict[str, Any] | None:
    feedback = handle_repetitive_feedback(text)
    if feedback:
        return feedback

    health = handle_health_data_query(text)
    if health:
        return health

    intent = detect_intent(text)
    if not intent:
        return None
    profile = load_profile()

    if intent == "crisis":
        append_log(intent, text, risk="crisis")
        return reply(
            "Fede: esto suena demasiado pesado para llevarlo solo. ¿Estás a salvo ahora mismo? "
            "Si hay riesgo de hacerte daño, llama a emergencias o a alguien de confianza ya."
        )

    if intent == "red_flag":
        append_log(intent, text, risk="medical_red_flag")
        return reply(
            "Fede: eso puede ser señal de alerta. No voy a interpretarlo por chat; si es intenso o brusco, busca atención médica urgente. ¿Está pasando ahora?"
        )

    if intent == "tinnitus":
        profile["health"]["tinnitus"]["red_flags_checked"] = True
        save_profile(profile)
        append_log(intent, text)
        return reply(
            "Fede: tinnitus unilateral por más de 6 meses es un dato importante. "
            "Como ya viste especialista, no invento causas. Hoy: sonido suave + rutina 10 min. "
            "¿Aumenta al apretar mandíbula o mover cuello?"
        )

    if intent == "supplements":
        append_log(intent, text)
        return reply(
            "Fede: los registro como suplementos, no tratamiento: melena de león, B12 complex y creatina. "
            "No asumo efecto clínico. Bitácora: sueño, ánimo, energía, tinnitus y tolerancia."
        )

    if intent == "sleep":
        append_log(intent, text)
        return reply(
            "Fede: para dormir bajemos fricción, no busquemos solución perfecta. "
            "Prueba 10 min: sonido bajo, almohada entre piernas, otra abrazada y luz mínima. "
            "¿Tinnitus 0-10 ahora?"
        )

    if intent == "micro_win":
        append_log(intent, text)
        return reply(
            "Fede: no parece enorme, pero cuenta. En días raros, avanzar algo, caminar o cuidar una comida también es señal de que sigues mirando hacia adelante."
        )

    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = handle(args.text) or {"status": "skip", "whatsapp_reply": ""}
    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out.get("whatsapp_reply", ""))


if __name__ == "__main__":
    main()
