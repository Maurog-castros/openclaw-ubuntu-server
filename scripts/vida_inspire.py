"""Frases cortas de filósofos/eruditos según perfil."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from vida_common import DATA, load_json, reply

QUOTES = {
    "estoico": [
        ("Epicteto", "No son las cosas las que perturban, sino la opinión que tenemos de ellas."),
        ("Marco Aurelio", "La calidad de tu día depende de la calidad de tus pensamientos."),
        ("Séneca", "No recibimos un espíritu débil; lo volvemos débil con el uso."),
    ],
    "reflexivo": [
        ("Kierkegaard", "La ansiedad es el vértigo de la libertad."),
        ("Camus", "Lo importante no es vivir, sino vivir bien."),
        ("Wittgenstein", "Los límites de mi lenguaje son los límites de mi mundo."),
    ],
    "disciplinado": [
        ("Aristóteles", "Somos lo que hacemos repetidamente. La excelencia no es un acto, sino un hábito."),
        ("William James", "Actúa como si lo que haces marcara diferencia. La marca."),
        ("Nietzsche", "Quien tiene un porqué puede soportar casi cualquier cómo."),
    ],
    "sensible": [
        ("Rilke", "Ten paciencia con lo que en ti no se resuelve."),
        ("Pascal", "Todo el mal del hombre viene de una sola cosa: no saber estar quieto."),
        ("Simone Weil", "La atención es la forma más rara y pura de generosidad."),
    ],
    "default": [
        ("Epicteto", "Haz lo que debes. Acepta lo que viene."),
        ("Spinoza", "No llorar, no reír, sino entender."),
    ],
}


def pick_quote(profile: dict) -> tuple[str, str]:
    traits = [t.lower() for t in profile.get("traits") or []]
    pool = []
    for trait in traits:
        if trait in QUOTES:
            pool.extend(QUOTES[trait])
    if not pool:
        tone = (profile.get("preferred_tone") or "").lower()
        if "sensible" in tone or "ansios" in tone:
            pool = QUOTES["sensible"]
        elif "disciplin" in tone:
            pool = QUOTES["disciplinado"]
        else:
            pool = QUOTES["default"]
    return random.choice(pool)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    profile = load_json(DATA / "profile.json", {})
    author, text = pick_quote(profile)
    out = reply(f"*{author}:* {text}")
    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
