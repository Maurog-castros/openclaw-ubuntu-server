"""Perfilado psicológico progresivo (1-2 preguntas por turno)."""
from __future__ import annotations

import argparse
import json

from vida_common import DATA, load_json, save_json, reply

QUESTIONS = [
    ("q_energy", "¿En qué momento del día sueles tener más energía: mañana, tarde o noche?"),
    ("q_stress", "¿Qué situación te desgasta más últimamente (trabajo, salud, familia, otro)?"),
    ("q_values", "¿Qué valor personal no quieres sacrificar aunque el día esté pesado?"),
    ("q_tone", "¿Prefieres que te hablen directo, suave, o con humor seco?"),
    ("q_traits", "¿Cómo te describirían dos personas que te conocen bien? (2 palabras cada una)"),
    ("q_routine", "¿Qué rutina pequeña te ayuda a sentirte bien aunque el día sea malo?"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="")
    ap.add_argument("--answer", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    profile = load_json(DATA / "profile.json", {})
    answers = profile.setdefault("answers", {})

    if args.answer and profile.get("last_question_id"):
        qid = profile["last_question_id"]
        answers[qid] = args.answer.strip()
        if qid == "q_traits":
            words = [w.strip() for w in args.answer.replace(",", " ").split() if w.strip()]
            profile["traits"] = list(dict.fromkeys((profile.get("traits") or []) + words[:6]))
        if qid == "q_values":
            profile["values"] = [args.answer.strip()]
        if qid == "q_tone":
            profile["preferred_tone"] = args.answer.strip()
        if qid == "q_energy":
            profile["energy_pattern"] = args.answer.strip()
        if qid == "q_stress":
            profile["stress_triggers"] = [args.answer.strip()]

    pending = [q for q, _ in QUESTIONS if q not in answers]
    if not pending:
        profile["onboarding_complete"] = True
        profile["last_question_id"] = None
        save_json(DATA / "profile.json", profile)
        out = reply("Perfil listo. A partir de ahora adapto tono, preguntas y citas a lo que me contaste.")
    else:
        qid, question = QUESTIONS[len(answers) % len(QUESTIONS)]
        if qid in answers:
            for qid, question in QUESTIONS:
                if qid not in answers:
                    break
        profile["last_question_id"] = qid
        save_json(DATA / "profile.json", profile)
        n = len(answers) + 1
        total = len(QUESTIONS)
        out = reply(f"Pregunta {n}/{total}: {question}")

    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
