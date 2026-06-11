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
