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
from openclaw_cli import openclaw_argv

BROH_PREFIX = re.compile(r"^\s*/broh\b\s*", re.I)
ADD_MEMORY_RE = re.compile(r"\b(recuerda|recordar|guarda|registr(?:a|ar)|anota)\b", re.I)
STATUS_RE = re.compile(r"\b(status|estado|contexto|historias|memoria)\b", re.I)
GREETING_RE = re.compile(r"^\s*(hola|buenas|como estas|cómo estás|que tal|qué tal)\??\s*$", re.I)
CHECKIN_RE = re.compile(r"\b(c[oó]mo va|como vamos|qué onda|que onda|todo bien|como andai|cómo andai)\b", re.I)
MOTIVATION_RE = re.compile(r"\b(motiva(?:dor|me|ción|cion)|motiviador|motivador|[aá]nimo|dime algo bueno|levantar el [aá]nimo)\b", re.I)
EXPLAIN_RE = re.compile(r"\b(que significa|qué significa|no entend[ií]|explica|a que te refieres|a qué te refieres)\b", re.I)
FEEDBACK_RE = re.compile(r"\b(wtf|no puedes decir otra cosa|otra cosa|muy repetitivo|repetitivo|no me sirve|mal)\b", re.I)
LONELY_RE = re.compile(r"\b(solito|solo|me siento solo|me siento solito|acompaña)\b", re.I)
NOISY_MEMORY_RE = re.compile(
    r"(\[image\]|\[telegram\b|<media:|inbound_event_kind|message_id|sender_id|chat_id|description:)",
    re.I,
)
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
    if NOISY_MEMORY_RE.search(cleaned):
        return False
    if len(cleaned.split()) <= SMALL_TALK_MAX_WORDS:
        return False
    if GREETING_RE.search(cleaned) or EXPLAIN_RE.search(cleaned) or FEEDBACK_RE.search(cleaned):
        return False
    return True


def should_store_conversation(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if NOISY_MEMORY_RE.search(cleaned):
        return False
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
    if CHECKIN_RE.search(text):
        return (
            "Broh:\n"
            "Va. Medio tarde, pero va.\n"
            "Te veo metido en mil frentes: agentes, pega, salud, ideas. Si quieres, hoy no hacemos informe; "
            "solo elegimos una cosa chica para dejar mejor encaminada."
        )
    if MOTIVATION_RE.search(text):
        return (
            "Broh:\n"
            "Algo motivador, pero sin humo: incluso cuando estás cansado, sigues construyendo criterio. "
            "No solo estás usando IA; estás armando un sistema propio alrededor de ella.\n"
            "Eso no es poca cosa."
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


STRUCTURED_CMD_RE = re.compile(
    r"^\s*/broh\b\s+(?:status|estado|contexto|historias|memoria|"
    r"recuerda|recordar|guarda|registr(?:a|ar)|anota|pulse|care)\b",
    re.I,
)
PULSE_CMD_RE = re.compile(r"\bpulse\b", re.I)
CARE_BRIDGE_RE = re.compile(r"\bcare\b", re.I)


BROH_SESSION_RE = re.compile(r"agent:broh:", re.I)
WHATSAPP_PEER_SESSION_RE = re.compile(
    r"(?:^|:)whatsapp(?::[^:\s]+)*:(\+\d{8,15})(?:$|[:\s])", re.I
)


def resolve_broh_session_key(session_key: str = "", peer: str = "") -> str:
    """Map main/whatsapp session keys to agent:broh:* (required by openclaw agent CLI)."""
    sk = (session_key or "").strip()
    if sk and BROH_SESSION_RE.search(sk):
        return sk
    if sk:
        wa = WHATSAPP_PEER_SESSION_RE.search(sk)
        if wa:
            return f"agent:broh:whatsapp:{wa.group(1)}"
        tg = re.search(r":telegram:(\d{5,})", sk)
        if tg:
            return f"agent:broh:telegram:{tg.group(1)}"
        rewritten = re.sub(r"^agent:[^:]+:", "agent:broh:", sk, count=1)
        if rewritten != sk:
            return rewritten
    phone = (peer or "").strip()
    if phone.startswith("telegram:"):
        return f"agent:broh:{phone}"
    if phone.startswith("+"):
        return f"agent:broh:whatsapp:{phone}"
    return "agent:broh:whatsapp"


def log_broh_route(route: str, reason: str, **extra: Any) -> None:
    parts = [f"route={route}", f"reason={reason}"]
    for key, value in extra.items():
        parts.append(f"{key}={value}")
    print(" ".join(parts), file=sys.stderr)


def is_structured_command(text: str) -> bool:
    return bool(STRUCTURED_CMD_RE.search(text or ""))


def extract_agent_text(payload: dict[str, Any]) -> str:
    for item in payload.get("payloads") or []:
        if isinstance(item, dict) and item.get("text"):
            return str(item["text"]).strip()
    return str(payload.get("whatsapp_reply") or payload.get("text") or "").strip()


def run_json_cmd(cmd: list[str], timeout: int = 180) -> tuple[int, dict[str, Any], str, str]:
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout, check=False)
    payload: dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"whatsapp_reply": proc.stdout.strip()}
    return proc.returncode, payload, proc.stdout, proc.stderr


def memory_context_brief(limit: int = 4) -> str:
    lines = [f"- {item.label}: {item.text}" for item in gather_evidence()[:limit]]
    if not lines:
        return ""
    return "Contexto reciente (usar con sutileza, no repetir literal):\n" + "\n".join(lines) + "\n\n"


def build_llm_prompt(user_text: str) -> str:
    body = BROH_PREFIX.sub("", user_text or "").strip() or (user_text or "").strip()
    instructions = (
        "Responde como Broh: cercano, directo, sobrio, chileno neutro. "
        "Usa memoria y diario solo como contexto; no los repitas literalmente salvo que sea util. "
        "Evita sonar filosofico si el usuario lo senala. "
        "Si el usuario da feedback sobre tu estilo, ajusta el tono de inmediato. "
        "Breve, humano y contextual. Empieza con Broh: si encaja.\n\n"
    )
    return instructions + memory_context_brief() + f"Mensaje de Mauro: {body}"


def maybe_store_conversation(user_text: str) -> None:
    body = BROH_PREFIX.sub("", user_text or "").strip() or (user_text or "").strip()
    if body and should_store_conversation(body):
        append_observation("conversation", body, story_id=detect_story(body))


def handle_structured(text: str) -> dict[str, Any]:
    body = BROH_PREFIX.sub("", text or "").strip()
    ensure_seed_stories()
    if PULSE_CMD_RE.search(body):
        code, payload, _, stderr = run_json_cmd(
            [sys.executable, str(ROOT / "scripts/broh_pulse.py"), "--dry-run", "--json"],
            timeout=120,
        )
        if code != 0 and not payload.get("message"):
            return reply(f"Broh: pulse no disponible. {stderr[-200:]}")
        msg = payload.get("message") or payload.get("reason") or "pulse listo"
        return reply(f"Broh: pulso proactivo — {msg}")
    if CARE_BRIDGE_RE.search(body):
        return reply(
            "Broh: para salud, diario, medicamentos y animo usa /care. "
            "Aqui sigo para compania y perspectiva narrativa."
        )
    if ADD_MEMORY_RE.search(text):
        return add_story_note(text)
    if STATUS_RE.search(body):
        return status_reply()
    return reply("Broh: comando no reconocido. Prueba /broh status o /broh recuerda ...")


def run_broh_llm(raw_text: str, session_key: str = "", peer: str = "") -> dict[str, Any]:
    maybe_store_conversation(raw_text)
    message = build_llm_prompt(raw_text)
    sk = resolve_broh_session_key(session_key, peer)
    code, payload, _, stderr = run_json_cmd(
        openclaw_argv(
            "agent",
            "--local",
            "--agent",
            "broh",
            "--session-key",
            sk,
            "--message",
            message,
            "--json",
        ),
        timeout=180,
    )
    reply_text = extract_agent_text(payload)
    if code != 0 or not reply_text:
        return {
            "status": "error",
            "agent": "broh",
            "route": "broh_llm",
            "whatsapp_reply": f"Broh: no pude responder ahora. {(stderr or '')[-250:]}",
        }
    return reply(reply_text, route="broh_llm")


def route_broh_message(raw_text: str, session_key: str = "", *, sticky: bool = False, peer: str = "") -> dict[str, Any]:
    if is_structured_command(raw_text):
        log_broh_route("broh_delegate", "explicit_structured_command", sticky=sticky)
        out = handle_structured(raw_text)
        out["route"] = "broh_delegate"
        return out
    log_broh_route("broh_llm", "conversational", sticky=sticky)
    return run_broh_llm(raw_text, session_key, peer)


def main() -> None:
    parser = argparse.ArgumentParser(description="Broh companion delegate.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--session-key", default="")
    parser.add_argument("--peer", default="")
    parser.add_argument("--structured-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ensure_seed_stories()
    if args.structured_only:
        if is_structured_command(args.text):
            out = handle_structured(args.text)
            out["route"] = "broh_delegate"
        else:
            out = {"status": "delegate_miss", "agent": "broh", "whatsapp_reply": ""}
    else:
        out = route_broh_message(args.text, args.session_key, peer=args.peer)

    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out.get("whatsapp_reply", ""))


if __name__ == "__main__":
    main()
