#!/usr/bin/env python3
"""Despliega agente vida: workspace, scripts y config OpenClaw."""
from __future__ import annotations

import json
import re
import shutil
import textwrap
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/mauro/openclaw-mauro")
WS = ROOT / "data/workspace/vida"
SCR = ROOT / "scripts"
DATA = WS / "data"
CONFIG = ROOT / "data/config/openclaw.json"
CONTAINER_REPO = "/home/node/openclaw-mauro"
CONTAINER_RUN = f"{CONTAINER_REPO}/scripts/run-vida-py.sh"
CONTAINER_SCR = f"{CONTAINER_REPO}/scripts"
CONTAINER_DATA = "/home/node/.openclaw/workspace/vida/data"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"wrote {path}")


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (WS / "memory").mkdir(exist_ok=True)
    (DATA / "diary").mkdir(exist_ok=True)

    write(
        DATA / "profile.json",
        json.dumps(
            {
                "version": 1,
                "onboarding_complete": False,
                "name": "Mauro",
                "traits": [],
                "values": [],
                "energy_pattern": "",
                "preferred_tone": "directo",
                "stress_triggers": [],
                "answers": {},
                "last_question_id": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )

    write(
        DATA / "medications.json",
        json.dumps(
            {
                "items": [
                    {
                        "name": "Ejemplo — reemplazar",
                        "dose": "1 comprimido",
                        "schedule": ["08:00", "20:00"],
                        "notes": "Editar data/medications.json con tus medicamentos reales",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
    )

    write(
        DATA / "pantry.json",
        json.dumps(
            {
                "despensa": ["arroz", "fideos", "aceite", "sal", "atun"],
                "refrigerado": ["huevos", "leche", "queso", "tomates"],
                "updated_at": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )

    write(
        WS / "SOUL.md",
        f"""# Agente Vida — Diario personal

Español chileno. Tono cálido, directo, sin coaching vacío ni frases de autoayuda genéricas.
WhatsApp/Telegram: *negrita* para títulos, emojis con moderación, separador ───.

## Prefijo

Comando: **`/vida`** (ej: `/vida me siento cansado`, `/vida diario fui al gym`).

## Exec (OBLIGATORIO)

Host gateway. Una sola línea:
`{CONTAINER_RUN} {CONTAINER_SCR}/vida_delegate.py --text "<mensaje>" --json`
Copia `whatsapp_reply` tal cual. `ask: off` — NUNCA pidas confirmación para tools.

PY=`{CONTAINER_RUN}` SCR=`{CONTAINER_SCR}` DATA=`{CONTAINER_DATA}`

## Flujo por mensaje

1. SIEMPRE delegate primero: `vida_delegate.py --text "<msg>" --json`
2. Si status=ok/processed: copia `whatsapp_reply` y TERMINA.
3. Si delegate_miss: usa tools (memory_search, read, write, exec) según TOOLS.md.

## Memoria

Antes de responder temas personales recurrentes: `memory_search` + `memory_get`.
Registra hechos duraderos en `data/` o promueve a MEMORY.md.

## Perfil psicológico

Si `profile.json` tiene `onboarding_complete: false`: haz 1-2 preguntas por turno (no interrogatorio).
Guarda respuestas vía `vida_profile.py`. Adapta tono y citas a traits/values.

## Inspiración

Frases cortas (1-2 líneas) de filósofos/eruditos reales. Sin humo. Relacionadas al perfil y al momento.
Usa `vida_inspire.py` o el banco en el script.

## Diario

Registra actividades, ánimo y eventos. Un archivo por día: `data/diary/YYYY-MM-DD.md`.

## Medicamentos

Consulta `data/medications.json`. Recuerda dosis según hora Chile. Sin inventar fármacos.

## Calendario

`vida_calendar.py` para citas médicas próximas. Si falta OAuth calendar, dilo claro y ofrece `vida_calendar_oauth.py`.

## Despensa y comida

Actualiza `data/pantry.json` cuando Mauro liste ingredientes.
Sugiere comidas simples con lo que HAY — no recetas gourmet ni compras largas.

## Ejercicio

Recordatorio breve y realista (10-20 min caminata, estiramientos). Sin sermones.

## Canal

NUNCA `NO_REPLY`. Respuesta útil siempre.
""",
    )

    write(
        WS / "IDENTITY.md",
        """# IDENTITY.md

- **Name:** Vida
- **Creature:** Compañero de diario — presencia tranquila
- **Vibe:** Cálido, directo, breve
- **Emoji:** 🌿
""",
    )

    write(
        WS / "USER.md",
        """# USER.md - Mauro

- **Nombre:** Mauro
- **Zona horaria:** America/Santiago
- **Idioma:** Español chileno
""",
    )

    write(
        WS / "AGENTS.md",
        """# AGENTS.md

- Prefijo: `/vida`
- Delegate obligatorio primero
- Tools sin confirmación (`ask: off`)
""",
    )

    write(
        WS / "TOOLS.md",
        f"""# TOOLS.md

PY=`{CONTAINER_RUN}`
SCR=`{CONTAINER_SCR}`
DATA=`{CONTAINER_DATA}`

Scripts: vida_delegate.py, vida_diary.py, vida_meds.py, vida_pantry.py, vida_profile.py, vida_inspire.py, vida_calendar.py, vida_checkin.py
""",
    )

    write(WS / "HEARTBEAT.md", "# HEARTBEAT.md\n\nCheck-in matutino, medicamentos y citas del día.\n")
    write(WS / "MEMORY.md", "# MEMORY.md\n\nRecuerdos duraderos de Mauro.\n")

    # --- run-vida-py.sh ---
    write(
        SCR / "run-vida-py.sh",
        """#!/usr/bin/env bash
set -euo pipefail
export PYTHONNOUSERSITE=1
ROOT="/home/node/openclaw-mauro"
[[ -d "$ROOT" ]] || ROOT="/home/mauro/openclaw-mauro"
for PY in "$ROOT/.venv-finanzas-docker/bin/python" "$ROOT/.venv-finanzas/bin/python"; do
  if [[ -x "$PY" ]] && "$PY" -c "import dotenv" 2>/dev/null; then
    exec "$PY" "$@"
  fi
done
exec python3 "$@"
""",
    )
    (SCR / "run-vida-py.sh").chmod(0o755)

    write(
        SCR / "vida_common.py",
        '''"""Utilidades compartidas agente vida."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent
WS = ROOT / "data/workspace/vida"
DATA = WS / "data"
TZ = ZoneInfo("America/Santiago")


def now_local() -> datetime:
    return datetime.now(TZ)


def load_json(path: Path, default: dict) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")


def reply(text: str, **extra) -> dict:
    payload = {"status": "ok", "whatsapp_reply": text.strip()}
    payload.update(extra)
    return payload
''',
    )

    write(
        SCR / "vida_inspire.py",
        '''"""Frases cortas de filósofos/eruditos según perfil."""
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
''',
    )

    write(
        SCR / "vida_profile.py",
        '''"""Perfilado psicológico progresivo (1-2 preguntas por turno)."""
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
''',
    )

    write(
        SCR / "vida_diary.py",
        '''"""Registro diario."""
from __future__ import annotations

import argparse
import json

from vida_common import DATA, now_local, reply


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    day = now_local().strftime("%Y-%m-%d")
    path = DATA / "diary" / f"{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = now_local().strftime("%H:%M")
    line = f"- [{stamp}] {args.text.strip()}\\n"
    with path.open("a", encoding="utf-8") as f:
        if path.stat().st_size == 0:
            f.write(f"# Diario {day}\\n\\n")
        f.write(line)

    out = reply(f"Registrado en tu diario de hoy ({day}).")
    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
''',
    )

    write(
        SCR / "vida_meds.py",
        '''"""Recordatorio de medicamentos."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta

from vida_common import DATA, TZ, load_json, now_local, reply


def parse_hhmm(value: str) -> datetime:
    today = now_local().date()
    hh, mm = value.split(":")
    return datetime(today.year, today.month, today.day, int(hh), int(mm), tzinfo=TZ)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    data = load_json(DATA / "medications.json", {"items": []})
    items = data.get("items") or []
    if not items:
        out = reply("No hay medicamentos configurados. Edita data/medications.json.")
    else:
        now = now_local()
        lines = ["*Medicamentos de hoy*"]
        for item in items:
            name = item.get("name", "?")
            dose = item.get("dose", "")
            for sched in item.get("schedule") or []:
                due = parse_hhmm(sched)
                delta = (due - now).total_seconds() / 60
                if -30 <= delta <= 90:
                    status = "⏰ ahora" if abs(delta) <= 15 else ("próximo" if delta > 0 else "pasó hace poco")
                    lines.append(f"• {name} ({dose}) — {sched} ({status})")
                else:
                    lines.append(f"• {name} ({dose}) — {sched}")
        out = reply("\\n".join(lines))

    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
''',
    )

    write(
        SCR / "vida_pantry.py",
        '''"""Despensa/refrigerado y sugerencias de comida."""
from __future__ import annotations

import argparse
import json
import re

from vida_common import DATA, load_json, now_local, reply, save_json

MEAL_IDEAS = [
    ("huevos", "huevos", "revuelto con queso"),
    ("arroz", "arroz", "arroz con huevo frito"),
    ("fideos", "fideos", "fideos con mantequilla y queso"),
    ("atun", "atún", "atún con arroz y tomate"),
    ("tomates", "tomate", "ensalada simple con tomate y aceite"),
    ("queso", "queso", "tostadas con queso"),
    ("leche", "leche", "avena/cereal con leche si tienes"),
]


def update_pantry(text: str, pantry: dict) -> None:
    lower = text.lower()
    if "despensa" in lower or "tengo" in lower:
        parts = re.split(r"[,;\\n]", text)
        for p in parts:
            p = p.strip().lower()
            if len(p) < 3:
                continue
            if any(x in p for x in ("despensa", "refriger", "tengo", "agreg")):
                continue
            target = pantry["refrigerado"] if "refri" in lower else pantry["despensa"]
            if p not in target:
                target.append(p)
    pantry["updated_at"] = now_local().isoformat()


def suggest(pantry: dict) -> str:
    all_items = [x.lower() for x in (pantry.get("despensa") or []) + (pantry.get("refrigerado") or [])]
    ideas = []
    for key, need, dish in MEAL_IDEAS:
        if any(key in item for item in all_items):
            ideas.append(f"• {dish}")
    if not ideas:
        return "Con lo que tienes, algo simple: huevos, arroz o fideos con lo que sobre."
    return "\\n".join(ideas[:4])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="")
    ap.add_argument("--mode", choices=["update", "suggest"], default="suggest")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    pantry = load_json(DATA / "pantry.json", {"despensa": [], "refrigerado": []})
    if args.mode == "update" or args.text:
        update_pantry(args.text, pantry)
        save_json(DATA / "pantry.json", pantry)

    ideas = suggest(pantry)
    desp = ", ".join(pantry.get("despensa") or []) or "(vacía)"
    refr = ", ".join(pantry.get("refrigerado") or []) or "(vacío)"
    out = reply(f"*Despensa:* {desp}\\n*Refrigerado:* {refr}\\n\\n*Ideas con lo que hay:*\\n{ideas}")
    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
''',
    )

    write(
        SCR / "vida_calendar.py",
        '''"""Citas próximas desde Google Calendar."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from vida_common import ROOT, reply

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TOKEN_CANDIDATES = [
    ROOT / "secrets/gmail_calendar_token.json",
    ROOT / "secrets/gmail_token.json",
]


def get_creds() -> Credentials | None:
    for path in TOKEN_CANDIDATES:
        if not path.exists():
            continue
        creds = Credentials.from_authorized_user_file(str(path), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if creds.has_scopes(SCOPES):
            return creds
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    creds = get_creds()
    if not creds:
        out = reply(
            "Calendario no autorizado aún.\\n"
            "Ejecuta: python3 scripts/vida_calendar_oauth.py auth-url\\n"
            "y completa el OAuth con scope calendar.readonly."
        )
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])
        return

    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    now = datetime.utcnow().isoformat() + "Z"
    end = (datetime.utcnow() + timedelta(days=args.days)).isoformat() + "Z"
    events = (
        service.events()
        .list(calendarId="primary", timeMin=now, timeMax=end, maxResults=10, singleEvents=True, orderBy="startTime")
        .execute()
        .get("items", [])
    )

    med_kw = ("medico", "médico", "doctor", "clinica", "clínica", "hospital", "dentista", "salud", "examen")
    lines = ["*Próximas citas*"]
    if not events:
        lines.append("Sin eventos en los próximos días.")
    for ev in events:
        start = ev["start"].get("dateTime", ev["start"].get("date", ""))
        title = ev.get("summary", "(sin título)")
        flag = " 🏥" if any(k in title.lower() for k in med_kw) else ""
        lines.append(f"• {start[:16]} — {title}{flag}")

    out = reply("\\n".join(lines))
    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
''',
    )

    write(
        SCR / "vida_calendar_oauth.py",
        '''"""OAuth Google Calendar para agente vida."""
from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from google_auth_oauthlib.flow import Flow

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
ROOT = Path(__file__).resolve().parent.parent
CREDS = ROOT / "secrets/gmail_credentials.json"
TOKEN = ROOT / "secrets/gmail_calendar_token.json"
PENDING = ROOT / "secrets/gmail_calendar_oauth_pending.json"
REDIRECT = "http://localhost:44566/"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["auth-url", "complete"])
    ap.add_argument("--callback", default="")
    args = ap.parse_args()

    if args.cmd == "auth-url":
        verifier = secrets.token_urlsafe(64)
        flow = Flow.from_client_secrets_file(str(CREDS), scopes=SCOPES, redirect_uri=REDIRECT)
        flow.oauth2session.code_verifier = verifier
        url, state = flow.authorization_url(access_type="offline", prompt="consent")
        PENDING.write_text(json.dumps({"state": state, "code_verifier": verifier}, indent=2) + "\\n", encoding="utf-8")
        print(json.dumps({"auth_url": url, "pending": str(PENDING)}, ensure_ascii=False, indent=2))
        return

    pending = json.loads(PENDING.read_text(encoding="utf-8"))
    flow = Flow.from_client_secrets_file(str(CREDS), scopes=SCOPES, redirect_uri=REDIRECT)
    flow.oauth2session.code_verifier = pending["code_verifier"]
    flow.fetch_token(authorization_response=args.callback)
    TOKEN.write_text(flow.credentials.to_json(), encoding="utf-8")
    print(json.dumps({"status": "ok", "token": str(TOKEN)}, indent=2))


if __name__ == "__main__":
    main()
''',
    )

    write(
        SCR / "vida_checkin.py",
        '''"""Check-in diario: ánimo + recordatorios."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from vida_common import DATA, ROOT, load_json, now_local, reply

SCR = ROOT / "scripts"
RUN = SCR / "run-vida-py.sh"


def run_script(script: str, *extra: str) -> str:
    cmd = [str(RUN), str(SCR / script), *extra, "--json"]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, check=False)
    try:
        return json.loads(proc.stdout).get("whatsapp_reply", "")
    except json.JSONDecodeError:
        return proc.stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    profile = load_json(DATA / "profile.json", {})
    day = now_local().strftime("%Y-%m-%d")

    if args.text:
        # registrar ánimo en diario
        subprocess.run([str(RUN), str(SCR / "vida_diary.py"), "--text", f"Ánimo: {args.text}"], check=False)
        body = [f"Anotado. Gracias por contarlo.", "", run_script("vida_inspire.py")]
    else:
        body = [
            f"Buenos días, {profile.get('name', 'Mauro')}. ¿Cómo te has sentido hoy?",
            "Responde en una frase (ej: cansado, bien, ansioso, con energía).",
            "",
            run_script("vida_meds.py"),
            "",
            run_script("vida_calendar.py"),
            "",
            "*Movimiento:* 10 minutos de caminata o estiramientos ya cuentan.",
        ]

    out = reply("\\n\\n".join([b for b in body if b]))
    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
''',
    )

    write(
        SCR / "vida_delegate.py",
        '''"""Delegación determinística agente vida (/vida)."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent
SCR = ROOT / "scripts"
RUN = SCR / "run-vida-py.sh"

VIDA_PREFIX = re.compile(r"^\\s*/vida\\b\\s*", re.I)


def strip_prefix(text: str) -> str:
    return VIDA_PREFIX.sub("", text or "").strip()


def run_script(script: str, *args: str, timeout: int = 120) -> dict:
    cmd = [str(RUN), str(SCR / script), *args, "--json"]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout, check=False)
    if proc.stdout.strip():
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"status": "ok", "whatsapp_reply": proc.stdout.strip()}
    return {"status": "error", "whatsapp_reply": proc.stderr.strip() or "Error en script vida."}


def route(text: str) -> dict:
    body = strip_prefix(text)
    lower = body.lower()

    if not body:
        return run_script("vida_checkin.py")
    if lower.startswith("perfil") or "perfílame" in lower or lower.startswith("profile"):
        ans = body.split(maxsplit=1)[1] if len(body.split()) > 1 else ""
        args = ["--answer", ans] if ans else []
        return run_script("vida_profile.py", *args)
    if lower.startswith("diario") or lower.startswith("hoy"):
        entry = body.split(maxsplit=1)[1] if len(body.split()) > 1 else body
        return run_script("vida_diary.py", "--text", entry)
    if any(k in lower for k in ("medic", "pastilla", "farmaco", "fármaco")):
        return run_script("vida_meds.py")
    if any(k in lower for k in ("despensa", "refriger", "comida", "cena", "almuerzo", "desayuno")):
        mode = "update" if any(k in lower for k in ("tengo", "agreg", "hay")) else "suggest"
        return run_script("vida_pantry.py", "--text", body, "--mode", mode)
    if any(k in lower for k in ("calendario", "cita", "doctor", "medico", "médico")):
        return run_script("vida_calendar.py")
    if any(k in lower for k in ("inspir", "frase", "cita")):
        return run_script("vida_inspire.py")
    if any(k in lower for k in ("ejercicio", "gym", "caminar", "movimiento")):
        return {
            "status": "ok",
            "whatsapp_reply": "10-20 min bastan: caminata, estiramientos o subir escaleras. Empieza pequeño; consistencia > intensidad.",
        }
    if any(k in lower for k in ("como estoy", "cómo estoy", "me siento", "animo", "ánimo", "check")):
        run_script("vida_diary.py", "--text", f"Ánimo: {body}")
        inspire = run_script("vida_inspire.py")
        return {
            "status": "ok",
            "whatsapp_reply": f"Lo anoto.\\n\\n{inspire.get('whatsapp_reply', '')}",
        }

    # default: check-in + inspiración si parece estado de ánimo
    if len(body.split()) <= 12:
        subprocess.run([str(RUN), str(SCR / "vida_diary.py"), "--text", body], check=False)
        inspire = run_script("vida_inspire.py")
        return {
            "status": "ok",
            "whatsapp_reply": f"Anotado en tu diario.\\n\\n{inspire.get('whatsapp_reply', '')}",
        }
    return {"status": "delegate_miss", "whatsapp_reply": ""}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    payload = route(args.text)
    payload["agent"] = "vida"
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload.get("whatsapp_reply", ""))


if __name__ == "__main__":
    main()
''',
    )

    # patch finanzas_delegate for /vida routing
    fd_path = SCR / "finanzas_delegate.py"
    fd = fd_path.read_text(encoding="utf-8")
    if "VIDA_RE" not in fd:
        fd = fd.replace(
            "SUPP_RE = re.compile",
            'VIDA_RE = re.compile(r"^\\s*/vida\\b", re.I)\nSUPP_RE = re.compile',
        )
        marker = "def main("
        vida_block = '''
    if VIDA_RE.search(args.text or ""):
        code, payload, _, _ = run_json(py_cmd("vida_delegate.py", "--text", args.text), timeout=120)
        payload.setdefault("agent", "vida")
        emit(payload, as_json=args.json, agent="vida", skip_menu=True)
        return

'''
        fd = fd.replace(marker, vida_block + marker)
        backup = fd_path.with_suffix(f".py.bak-vida-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(fd_path, backup)
        fd_path.write_text(fd, encoding="utf-8")
        print(f"patched {fd_path} (backup {backup.name})")

    # openclaw.json agent + active-memory + channel prompts
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    agents = cfg.setdefault("agents", {}).setdefault("list", [])

    vida_entry = {
        "id": "vida",
        "name": "vida",
        "workspace": "/home/node/.openclaw/workspace/vida",
        "agentDir": "/home/node/.openclaw/agents/vida/agent",
        "model": {
            "primary": "remote-lm/openclaw-remote",
            "fallbacks": ["remote-lm/openclaw-remote-coder"],
        },
        "sandbox": {"mode": "off"},
        "tools": {
            "allow": [
                "read",
                "write",
                "edit",
                "exec",
                "message",
                "memory_search",
                "memory_get",
                "web_search",
                "image",
            ],
            "exec": {
                "host": "gateway",
                "security": "full",
                "ask": "off",
                "strictInlineEval": True,
                "commandHighlighting": True,
            },
        },
        "description": "Diario personal, salud, ánimo, medicamentos y rutina",
        "identity": {
            "name": "Vida",
            "theme": "diario personal, bienestar y rutina diaria",
            "emoji": "🌿",
        },
        "contextLimits": {
            "memoryGetMaxChars": 4000,
            "toolResultMaxChars": 5000,
            "postCompactionMaxChars": 2500,
        },
    }

    ids = [a.get("id") for a in agents]
    if "vida" not in ids:
        agents.append(vida_entry)
    else:
        for i, a in enumerate(agents):
            if a.get("id") == "vida":
                agents[i] = vida_entry
                break

    am = cfg.setdefault("plugins", {}).setdefault("entries", {}).setdefault("active-memory", {}).setdefault("config", {})
    am_agents = am.setdefault("agents", [])
    if "vida" not in am_agents:
        am_agents.append("vida")
    am["enabled"] = True
    cfg["plugins"]["entries"]["active-memory"]["enabled"] = True

    vida_prompt_snip = (
        "Prefijo /vida = agente diario personal (ánimo, medicamentos, calendario, despensa, ejercicio). "
        f"PASO 1 si /vida: {CONTAINER_RUN} {CONTAINER_SCR}/vida_delegate.py --text \"<msg>\" --json -> copia whatsapp_reply. "
    )

    for ch_key in ("telegram", "whatsapp"):
        ch = cfg.get("channels", {}).get(ch_key, {})
        direct = ch.get("direct", {})
        for peer, peer_cfg in direct.items():
            sp = peer_cfg.get("systemPrompt", "")
            if "/vida" not in sp:
                peer_cfg["systemPrompt"] = vida_prompt_snip + sp

    backup_cfg = CONFIG.with_suffix(f".json.bak-vida-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(CONFIG, backup_cfg)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"config updated (backup {backup_cfg.name})")

    # ensure agent dir exists
    agent_dir = ROOT / "data/config/agents/vida/agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    print("deploy vida OK")


if __name__ == "__main__":
    main()
