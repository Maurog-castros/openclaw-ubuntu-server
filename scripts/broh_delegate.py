#!/usr/bin/env python3
"""Delegado narrativo /broh: compañía, perspectiva y memoria de continuidad."""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from vida_common import ROOT, now_local, truncate_whatsapp

BROH_PREFIX = re.compile(r"^\s*/broh\b\s*", re.I)
ADD_MEMORY_RE = re.compile(r"\b(recuerda|recordar|guarda|registr(?:a|ar)|anota)\b", re.I)
STATUS_RE = re.compile(r"\b(status|estado|contexto|historias|memoria)\b", re.I)
GREETING_RE = re.compile(r"^\s*(hola|buenas|como estas|cómo estás|que tal|qué tal)\??\s*$", re.I)
EXPLAIN_RE = re.compile(r"\b(que significa|qué significa|no entend[ií]|explica|a que te refieres|a qué te refieres)\b", re.I)
FEEDBACK_RE = re.compile(r"\b(wtf|no puedes decir otra cosa|otra cosa|muy repetitivo|repetitivo|no me sirve|mal)\b", re.I)
LONELY_RE = re.compile(r"\b(solito|solo|me siento solo|me siento solito|acompaña)\b", re.I)
SMALL_TALK_MAX_WORDS = 8
STORY_KEYS = {
    "tinnitus": re.compile(r"\b(tinnitus|oido|oído|zumbido|sonido)\b", re.I),
    "career_transition": re.compile(r"\b(trabajo|postul|entrevista|linkedin|cv|empleo|jobs)\b", re.I),
    "agents_project": re.compile(r"\b(openclaw|agentes?|ia|broh|care|jobs|hlgo)\b", re.I),
    "learning": re.compile(r"\b(aprender|estudiar|curso|fundamentos|tecnolog)\b", re.I),
}


@dataclass(frozen=True)
class Evidence:
    label: str
    text: str


def user_data_root() -> Path:
    override = os.environ.get("OPENCLAW_USER_DATA_ROOT", "").strip()
    if override:
        return Path(override)
    return ROOT / "data"


def broh_data() -> Path:
    override = os.environ.get("OPENCLAW_USER_BROH_DATA", "").strip()
    if override:
        return Path(override)
    return user_data_root() / "workspace/broh/data"


def story_path() -> Path:
    return broh_data() / "stories.json"


def observations_path() -> Path:
    return broh_data() / "observations.jsonl"


def ensure_seed_stories() -> list[dict[str, Any]]:
    path = story_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    stories = [
        {
            "id": "tinnitus",
            "title": "Tinnitus y descanso",
            "summary": "Mauro viene registrando molestias de oído/tinnitus y algunas noches de sueño difícil.",
            "tone": "acompañar sin diagnosticar; derivar lo médico a /care",
        },
        {
            "id": "career_transition",
            "title": "Transición profesional",
            "summary": "Está evaluando nuevas oportunidades técnicas, postulaciones y formas de mostrar mejor su experiencia.",
            "tone": "mirar progreso real sin vender humo",
        },
        {
            "id": "agents_project",
            "title": "OpenClaw como línea propia",
            "summary": "Está construyendo agentes especializados para convertir automatización e IA en una plataforma personal útil.",
            "tone": "reconocer continuidad técnica y foco",
        },
        {
            "id": "learning",
            "title": "Aprendizaje desde fundamentos",
            "summary": "Valora entender la tecnología desde la base y no depender ciegamente de automatización.",
            "tone": "reforzar criterio y paciencia",
        },
    ]
    save_json(path, stories)
    return stories


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_observation(kind: str, text: str, *, story_id: str | None = None) -> None:
    observations_path().parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": now_local().isoformat(timespec="seconds"),
        "kind": kind,
        "story_id": story_id,
        "text": re.sub(r"\s+", " ", text).strip()[:800],
    }
    with observations_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def detect_story(text: str) -> str | None:
    for story_id, pattern in STORY_KEYS.items():
        if pattern.search(text or ""):
            return story_id
    return None


def add_story_note(text: str) -> dict[str, Any]:
    cleaned = ADD_MEMORY_RE.sub("", BROH_PREFIX.sub("", text or ""), count=1).strip(" :.-")
    if not cleaned:
        return reply("Broh: dime que quieres que recuerde y lo dejo como parte de la historia.")
    story_id = detect_story(cleaned) or "life_context"
    stories = ensure_seed_stories()
    if not any(item.get("id") == story_id for item in stories):
        stories.append(
            {
                "id": story_id,
                "title": "Contexto de vida",
                "summary": cleaned,
                "tone": "acompañar con perspectiva",
            }
        )
    append_observation("user_note", cleaned, story_id=story_id)
    save_json(story_path(), stories)
    return reply(f"Broh: lo guardé en la historia `{story_id}`. No lo voy a usar como dato suelto, sino como contexto.")


def recent_diary(days: int = 7) -> list[Evidence]:
    base = Path(os.environ.get("OPENCLAW_USER_CARE_DATA", "")) if os.environ.get("OPENCLAW_USER_CARE_DATA") else ROOT / "data/workspace/care/data"
    diary = base / "diary"
    out: list[Evidence] = []
    today = now_local().date()
    for offset in range(days):
        path = diary / f"{today - timedelta(days=offset):%Y-%m-%d}.md"
        if not path.exists():
            continue
        for raw in reversed(path.read_text(encoding="utf-8").splitlines()):
            text = re.sub(r"^\s*-\s*\[\d{2}:\d{2}\]\s*", "", raw).strip()
            text = re.sub(r"\s+", " ", text)
            lower = text.lower()
            if (
                len(text) >= 18
                and not text.startswith("#")
                and not lower.startswith("ánimo:")
                and not lower.startswith("animo:")
            ):
                out.append(Evidence("diario", text[:130]))
                break
        if len(out) >= 2:
            break
    return out


def recent_jobs() -> list[Evidence]:
    candidates = [
        ROOT / "data/workspace/jobs/applications.csv",
        ROOT / "data/jobs/applications.csv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            rows = list(csv.DictReader(path.open(encoding="utf-8")))
        except csv.Error:
            return []
        out: list[Evidence] = []
        for row in rows[-3:]:
            title = row.get("title") or row.get("cargo") or row.get("company") or row.get("url") or ""
            status = row.get("status") or row.get("estado") or "registrada"
            if title and not title.startswith("http") and str(status).lower() not in {"skip", "omitida"}:
                out.append(Evidence("jobs", f"{title[:80]} ({status})"))
        return out[-2:]
    return []


def git_evidence(repo: Path, label: str) -> Evidence | None:
    if not (repo / ".git").exists():
        return None
    proc = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--date=format-local:%d-%m %H:%M", "--pretty=format:%ad %h %s"],
        text=True,
        capture_output=True,
        timeout=12,
        check=False,
    )
    text = (proc.stdout or "").strip()
    return Evidence(label, text[:160]) if text else None


def recent_technical_work() -> list[Evidence]:
    out: list[Evidence] = []
    for repo, label in (
        (Path("/home/mauro/Dev/openclaw-mauro"), "openclaw"),
        (Path("/home/mauro/Dev/hl_miko"), "hl-go"),
    ):
        found = git_evidence(repo, label)
        if found:
            out.append(found)
    return out


def observations(limit: int = 3) -> list[Evidence]:
    path = observations_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    out: list[Evidence] = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = str(row.get("text") or "").strip()
        if text and useful_observation(text):
            out.append(Evidence("memoria", text[:160]))
    return out


def useful_observation(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned.split()) <= SMALL_TALK_MAX_WORDS:
        return False
    if GREETING_RE.search(cleaned) or EXPLAIN_RE.search(cleaned) or FEEDBACK_RE.search(cleaned):
        return False
    return True


def should_store_conversation(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not useful_observation(cleaned):
        return False
    return detect_story(cleaned) is not None or len(cleaned) >= 90


def gather_evidence() -> list[Evidence]:
    data = []
    data.extend(observations())
    data.extend(recent_diary())
    data.extend(recent_jobs())
    data.extend(recent_technical_work())
    seen: set[str] = set()
    unique: list[Evidence] = []
    for item in data:
        key = f"{item.label}:{item.text.lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:5]


def status_reply() -> dict[str, Any]:
    stories = ensure_seed_stories()
    lines = ["Broh: tengo estas historias vivas:"]
    lines.extend(f"* {item['id']}: {item['summary'][:120]}" for item in stories[:4])
    evidence = gather_evidence()[:3]
    if evidence:
        lines.append("Últimas señales:")
        lines.extend(f"* {item.label}: {item.text[:110]}" for item in evidence)
    return reply("\n".join(lines))


def casual_reply(text: str) -> str | None:
    if FEEDBACK_RE.search(text):
        return (
            "Broh:\n"
            "Sí, tienes razón. Me fui en modo resumen de evidencia y soné como plantilla.\n"
            "Versión simple: estoy aquí contigo. Puedo hablar más normal, tirar una talla suave, "
            "o ayudarte a ordenar lo que tienes en la cabeza."
        )
    if EXPLAIN_RE.search(text):
        return (
            "Broh:\n"
            "Quise decir esto: aunque hoy se sienta raro o lento, no estás parado. "
            "Has seguido haciendo cosas concretas: salud, pega, OpenClaw, ideas.\n"
            "Pero sí, lo dije medio solemne."
        )
    if GREETING_RE.search(text):
        return (
            "Broh:\n"
            "Aquí, atento. No tengo un 'estado de ánimo' real, pero estoy para acompañarte un rato.\n"
            "¿Quieres que conversemos liviano o prefieres que miremos algo que te esté pesando?"
        )
    if LONELY_RE.search(text):
        return (
            "Broh:\n"
            "Te leo. No voy a llenarte de frases bonitas.\n"
            "Quedémonos en algo simple: no tienes que resolver la vida ahora. Podemos conversar un rato, "
            "ordenar una idea, o simplemente bajar un cambio."
        )
    return None


def build_perspective(user_text: str = "") -> str:
    stories = ensure_seed_stories()
    story_id = detect_story(user_text) or random.choice([item["id"] for item in stories])
    story = next((item for item in stories if item.get("id") == story_id), stories[0])
    evidence = gather_evidence()
    if user_text != "pulso proactivo" and should_store_conversation(user_text):
        append_observation("conversation", user_text, story_id=story_id)

    lines = ["Broh:"]
    if evidence:
        chosen = evidence[:3]
        lines.append("Estoy mirando señales concretas:")
        lines.extend(f"* {item.label}: {item.text[:115]}" for item in chosen)
    else:
        lines.append("No tengo muchas señales recientes, pero sí tengo la historia larga.")

    summary = str(story.get("summary") or "")
    if story_id == "tinnitus":
        lines.append(
            "No voy a jugar al doctor con eso. Lo que sí veo es que has seguido registrando y buscando orden incluso con ruido encima."
        )
    elif story_id == "career_transition":
        lines.append(
            "Desde dentro puede sentirse lento. Desde fuera se ve una persona que sigue abriendo puertas y ajustando el relato profesional."
        )
    elif story_id == "agents_project":
        lines.append(
            "OpenClaw no es solo cacharreo: estás separando agentes, memoria y rutinas. Eso ya parece sistema, no ocurrencia."
        )
    else:
        lines.append(f"La historia de fondo es esta: {summary}")

    lines.append("No puedo vivirlo por ti, pero sí puedo recordarte continuidad: hoy no estás partiendo de cero.")
    return "\n".join(lines)


def reply(text: str, **extra: Any) -> dict[str, Any]:
    payload = {"status": "ok", "agent": "broh", "whatsapp_reply": truncate_broh(text)}
    payload.update(extra)
    return payload


def truncate_broh(text: str, max_len: int = 500) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in (text or "").splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[: max_len + 1].rsplit(" ", 1)[0]
    if not cut or len(cut) < max_len // 2:
        cut = cleaned[:max_len]
    return cut.rstrip(".,;:- ") + "..."


def main() -> None:
    parser = argparse.ArgumentParser(description="Broh companion delegate.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    text = BROH_PREFIX.sub("", args.text or "").strip()
    ensure_seed_stories()

    if ADD_MEMORY_RE.search(text):
        out = add_story_note(text)
    elif STATUS_RE.search(text):
        out = status_reply()
    elif casual := casual_reply(text):
        out = reply(casual)
    else:
        out = reply(build_perspective(text))

    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
