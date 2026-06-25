"""Detección de intención para enrutar mensajes WhatsApp sin prefijo /agent."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from datetime import date
from pathlib import Path
from typing import Optional

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent

STICKY_STATE = ROOT / "data/whatsapp_last_agent.json"


def sticky_state_path() -> Path:
    override = os.environ.get("OPENCLAW_USER_STICKY_FILE", "").strip()
    if override:
        return Path(override)
    return STICKY_STATE

# --- Prefijos explícitos (máxima prioridad, manejados en channel_delegate) ---
PREFIX_CARE = re.compile(r"/care\b", re.I)
PREFIX_BROH = re.compile(r"/broh\b", re.I)
PREFIX_SUPP = re.compile(r"/supp\b", re.I)
PREFIX_INTEL = re.compile(r"/intel\b", re.I)
PREFIX_JOBS = re.compile(r"/(?:jobs|postula)\b", re.I)
PREFIX_HLGO = re.compile(r"/(?:hlgo|hl-go|hl)\b", re.I)
PREFIX_JENKI = re.compile(r"/jenki\b", re.I)
PREFIX_CONTENT = re.compile(r"/content\b", re.I)
PREFIX_PYME = re.compile(r"/(?:pyme(?:-chile)?|pymechile)\b", re.I)
PREFIX_FIN = re.compile(r"/(?:fin|finanzas)\b", re.I)

AGENT_COMMAND_LABELS = {
    "fin": "/fin",
    "care": "/care",
    "broh": "/broh",
    "supp": "/supp",
    "intel": "/intel",
    "jobs": "/jobs",
    "hlgo": "/hlgo",
    "content": "/content",
    "jenki": "/jenki",
    "pyme-chile": "/pyme",
}

# --- Finanzas (default) ---
FIN_SALDO_RE = re.compile(
    r"\b(saldo|cuenta\s+corriente|santander|disponible|dame\s+(?:el\s+)?saldo|"
    r"cu[aá]nto\s+tengo|mi\s+saldo|saldo\s+real|captura|screenshot|"
    r"actualiz(?:ar|a)\s+(?:mi\s+)?saldo)\b",
    re.I,
)
FIN_TRANSFERENCIAS_RE = re.compile(
    r"\b(transferencias?|movimientos?\s+bancari|movimientos?\s+del\s+banco|"
    r"movimientos?\s+recientes|cartola|giros?\s+(?:salida|enviados?)|"
    r"depositos?|abonos?|cargos?\s+bancari|ultim(?:os|as)\s+movimientos?)\b",
    re.I,
)
FIN_GASTOS_RE = re.compile(
    r"\b(gastos?\s+(?:del?\s+)?mes|cu[aá]nto\s+gast[eé]|gast[eé]\s+en\s+|"
    r"resumen\s+mensual|gasto\s+total|cu[aá]nto\s+llev(?:o|amos)\s+gastado)\b",
    re.I,
)
FIN_BOLETAS_RE = re.compile(
    r"\b(boletas?|ticket|compra|recibo|supermercado|farmacia|minimarket|"
    r"ultim(?:as|os)\s+boletas?)\b",
    re.I,
)
FIN_DEDUPE_RE = re.compile(
    r"\b(duplicad|mismo\s+monto|otra\s+vez|corrige|es\s+la\s+misma|misma\s+transacc)\b",
    re.I,
)
FIN_TRANSFER_EMAIL_RE = re.compile(
    r"(mensajeria@santander|@santander\.cl|monto\s+transferido|"
    r"comprobante\s+transferencia|notificaci[oó]n\s+de\s+transferencia|"
    r"datos\s+de\s+origen|datos\s+del\s+ordenante)",
    re.I,
)
FIN_INSTAGRAM_URL_RE = re.compile(r"instagram\.com/(?:p|reel|reels)/", re.I)

# --- Care ---
CARE_RE = re.compile(
    r"\b(medic|pastilla|f[aá]rmaco|diario|despensa|refriger|comida|cena|almuerzo|"
    r"desayuno|calendario|citas?\s+m[eé]dic|agenda\s+m[eé]dic|doctor|m[eé]dico|"
    r"examen|laboratorio|orden\s+m[eé]dic|me\s+siento|c[oó]mo\s+estoy|"
    r"[aá]nimo|check[\s-]?in|ejercicio|gym|caminar|inspir|frase\s+del\s+d[ií]a|"
    r"perfil(?:ame)?)\b",
    re.I,
)
CARE_EXAM_MEDIA_RE = re.compile(
    r"\b(examen|laboratorio|orden|agenda|cita|toma)\b",
    re.I,
)
CARE_CHECKIN_FOLLOWUP_RE = re.compile(
    r"(?:"
    r"\bfede\b.*\b(?:care|/care)\b|"
    r"(?:^|\s)/care\b|"
    r"ánimo\s*0\s*[-–]\s*10|"
    r"animo\s*0\s*[-–]\s*10|"
    r"cerrar\s+el\s+d[ií]a|"
    r"no\s+necesitas\s+resolver\s+todo|"
    r"mismo\s+consejo|"
    r"siempre\s+(?:me\s+)?(?:das|dices)\s+(?:lo\s+mismo|el\s+mismo)|"
    r"evidencia\s+de\s+que\s+sigues\s+cuid|"
    r"datos\s+de\s+salud|"
    r"ultim(?:os|as)\s+(?:datos|registros?).*salud|"
    r"qu[eé]\s+registr(?:aste|ó)|"
    r"registr(?:aste|ó).*(?:salud|autocuidado)"
    r")",
    re.I,
)


def is_care_checkin_followup(text: str) -> bool:
    return bool(CARE_CHECKIN_FOLLOWUP_RE.search(text or ""))

# --- Broh ---
BROH_RE = re.compile(
    r"\b(broh|compa(?:ñero)?|perspectiva|me\s+siento\s+solo|solito|acompaña(?:me)?|"
    r"reconocimiento|mirar\s+desde\s+fuera|continuidad|proceso\s+de\s+vida)\b",
    re.I,
)

# --- Supp ---
SUPP_RE = re.compile(
    r"\b(soporte\s+tecnico|soporte\s+openclaw|gateway|openclaw|"
    r"logs?|escanear|auto-?fix|arregla(?:r)?|remediar|soluciona(?:r)?|"
    r"agente\s+(?:atascado|pegado)|sesion\s+atascada|estado\s+del\s+sistema|"
    r"estado\s+sistema|cron\s*jobs?|crons?|whatsapp\s+pending)\b",
    re.I,
)

# --- Intel ---
INTEL_RE = re.compile(
    r"\b(radar|tendencias|intel\s+daily|reporte\s+consolidad|linkedin\s+intel|"
    r"que\s+paso\s+hoy|devops|innovaci[oó]n\s*radical|senales\s+linkedin|"
    r"señales\s+linkedin|github\s+intel|resum(?:e|ir)\s+(?:el\s+)?video|youtube)\b",
    re.I,
)
YOUTUBE_URL_RE = re.compile(r"(?:youtube\.com|youtu\.be)", re.I)
JOBS_RE = re.compile(
    r"\b(vacantes?|postular|postula|postulacion|oportunidad\s+laboral|buscar\s+trabajo|"
    r"empleo\s+devops|cv\s+para|aplicar\s+a|cover\s+letter|match\s+vacantes?)\b",
    re.I,
)
HLGO_RE = re.compile(
    r"\b(hl[\s-]?go|hl_miko|h-l\s+solutions|planilla\s+go|remesa\s+hl|"
    r"import\s+tracking|logistica\s+hl)\b",
    re.I,
)

# --- Content ---
CONTENT_URL_RE = re.compile(r"instagram\.com/(?:p|reel|reels)/", re.I)
CONTENT_FOLLOWUP_RE = re.compile(
    r"\b(ultim[oa]\s+post|ese\s+post|de\s+qu[eé]\s+trata|resumen\s+del\s+post)\b",
    re.I,
)


def normalize_routing_text(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^\[(?:WhatsApp|Telegram)[^\]]*\]\s*", "", t, flags=re.I)
    t = re.sub(r"^\+\d{10,15}:\s*", "", t)
    return t.strip()


def explicit_prefix(text: str) -> Optional[str]:
    t = normalize_routing_text(text)
    if PREFIX_CARE.search(t):
        return "care"
    if PREFIX_BROH.search(t):
        return "broh"
    if PREFIX_SUPP.search(t):
        return "supp"
    if PREFIX_INTEL.search(t):
        return "intel"
    if PREFIX_JOBS.search(t):
        return "jobs"
    if PREFIX_HLGO.search(t):
        return "hlgo"
    if PREFIX_JENKI.search(t):
        return "jenki"
    if PREFIX_CONTENT.search(t):
        return "content"
    if PREFIX_PYME.search(t):
        return "pyme-chile"
    if PREFIX_FIN.search(t):
        return "fin"
    return None


def apply_explicit_agent_switch(text: str) -> tuple[Optional[str], Optional[str], bool]:
    """Guarda sticky al detectar /agente. Devuelve (nuevo, anterior, cambio)."""
    previous = current_sticky_agent()
    explicit = explicit_prefix(text)
    if not explicit:
        return None, previous, False
    switched = bool(previous and previous != explicit)
    save_sticky_agent(explicit)
    return explicit, previous, switched


def agent_switch_notice(previous: Optional[str], new: Optional[str]) -> str:
    if not new or not previous or previous == new:
        return ""
    old_label = AGENT_COMMAND_LABELS.get(previous, f"/{previous}")
    new_label = AGENT_COMMAND_LABELS.get(new, f"/{new}")
    return f"Hilo: {old_label} → {new_label} (cambio automatico)\n\n"


def reset_openclaw_session_for_switch(session_key: str) -> bool:
    """Archiva la sesión OpenClaw del canal al cambiar /agente (sin reiniciar gateway)."""
    key = (session_key or "").strip()
    if not key:
        return False
    agents_dir = ROOT / "data/config/agents"
    if not agents_dir.exists():
        return False
    stamp = time.strftime("%Y%m%d-%H%M%S")
    removed = False
    for sessions_json in agents_dir.glob("*/sessions/sessions.json"):
        try:
            data = json.loads(sessions_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        entry = data.pop(key, None)
        if not entry:
            continue
        removed = True
        try:
            backup = sessions_json.with_suffix(f".json.bak-agent-switch-{stamp}")
            shutil.copy2(sessions_json, backup)
        except OSError:
            pass
        sessions_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sid = str(entry.get("sessionId") or "").strip()
        if sid:
            base = sessions_json.parent
            for pattern in (f"{sid}.jsonl", f"{sid}.trajectory.jsonl", f"{sid}.trajectory-path.json"):
                path = base / pattern
                if path.exists():
                    try:
                        path.rename(path.with_name(path.name + f".bak-agent-switch-{stamp}"))
                    except OSError:
                        pass
    return removed


STICKY_AGENTS = frozenset({"fin", "care", "broh", "supp", "intel", "jobs", "hlgo", "content", "jenki", "pyme-chile"})


def _load_sticky() -> tuple[Optional[str], float]:
    path = sticky_state_path()
    if not path.exists():
        return None, 0.0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        agent = data.get("agent")
        ts = float(data.get("updated_at_ts") or 0)
        if agent in STICKY_AGENTS:
            return str(agent), ts
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None, 0.0


def current_sticky_agent() -> Optional[str]:
    sticky, _ = _load_sticky()
    return sticky


def save_sticky_agent(agent: str) -> None:
    if agent not in STICKY_AGENTS:
        return
    path = sticky_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"agent": agent, "updated_at_ts": time.time()}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def clear_sticky_agent() -> None:
    path = sticky_state_path()
    if path.exists():
        path.unlink()


def score_agents(text: str, *, has_media: bool = False) -> dict[str, int]:
    t = (text or "").strip()
    lower = t.lower()
    scores: dict[str, int] = {
        "fin": 0, "care": 0, "broh": 0, "supp": 0, "intel": 0, "jobs": 0, "hlgo": 0, "content": 0, "jenki": 0, "pyme-chile": 0,
    }

    if FIN_SALDO_RE.search(t):
        scores["fin"] += 3
    if FIN_TRANSFERENCIAS_RE.search(t):
        scores["fin"] += 4
    if FIN_GASTOS_RE.search(t):
        scores["fin"] += 3
    if FIN_BOLETAS_RE.search(t):
        scores["fin"] += 3
    if FIN_DEDUPE_RE.search(t):
        scores["fin"] += 2
    if len(t) >= 80 and FIN_TRANSFER_EMAIL_RE.search(t):
        scores["fin"] += 6

    if CARE_RE.search(t):
        scores["care"] += 3
    if is_care_checkin_followup(t):
        scores["care"] += 8
    if has_media and (CARE_EXAM_MEDIA_RE.search(t) or not t):
        scores["care"] += 2
    if BROH_RE.search(t):
        scores["broh"] += 4

    if SUPP_RE.search(t):
        scores["supp"] += 4

    if INTEL_RE.search(t):
        scores["intel"] += 4
    if YOUTUBE_URL_RE.search(t):
        scores["intel"] += 6
    if JOBS_RE.search(t):
        scores["jobs"] += 5
    if HLGO_RE.search(t):
        scores["hlgo"] += 6
    if re.search(r"\b(jenkins|jenki|pipeline|ci/cd|terraform|minikube|aws|ubuntu)\b", t, re.I):
        scores["jenki"] += 6

    if CONTENT_URL_RE.search(t) or CONTENT_FOLLOWUP_RE.search(t):
        scores["content"] += 5

    if PREFIX_PYME.search(t) or re.search(r"\b(sercotec|corfo|fosis|chileatiende|pyme|capital\s+semilla|ferias?\s+libres?)\b", t, re.I):
        scores["pyme-chile"] += 6

    # Foto sin texto: fin (boleta/saldo) salvo keywords care
    if has_media and len(t) < 40:
        if CARE_EXAM_MEDIA_RE.search(t):
            scores["care"] += 3
        elif FIN_SALDO_RE.search(t):
            scores["fin"] += 3
        else:
            scores["fin"] += 1

    # Mensajes muy cortos ambiguos
    if len(lower.split()) <= 2 and lower in {"status", "estado", "help", "ayuda", "fix", "scan"}:
        scores["supp"] += 3

    return scores


def detect_agent(
    text: str,
    *,
    has_media: bool = False,
    use_sticky: bool = True,
    apply_switch: bool = True,
) -> str:
    """Devuelve agent destino. Hilo: prefijo explícito o sticky hasta /new, /reset u otro prefijo."""
    if apply_switch:
        explicit, _, _ = apply_explicit_agent_switch(text)
    else:
        explicit = explicit_prefix(text)
    if explicit:
        return explicit

    if is_care_checkin_followup(text):
        save_sticky_agent("care")
        return "care"

    # Foto adjunta => fin (boleta/saldo). No heredar sticky jobs/intel/etc.
    if has_media and not CARE_EXAM_MEDIA_RE.search(text or ""):
        save_sticky_agent("fin")
        return "fin"

    if use_sticky:
        sticky, _ = _load_sticky()
        if sticky:
            return sticky

    scores = score_agents(text, has_media=has_media)
    best_agent = max(scores, key=lambda k: scores[k])
    best_score = scores[best_agent]

    if best_score > 0:
        tied = [a for a, s in scores.items() if s == best_score]
        if len(tied) > 1:
            for preferred in ("pyme-chile", "content", "hlgo", "jobs", "jenki", "supp", "intel", "broh", "care", "fin"):
                if preferred in tied:
                    best_agent = preferred
                    break
        return best_agent

    return "fin"


def strip_agent_prefix(text: str, agent: str) -> str:
    t = normalize_routing_text(text or "")
    if agent == "fin":
        return PREFIX_FIN.sub("", t).strip()
    if agent == "care":
        return PREFIX_CARE.sub("", t).strip()
    if agent == "broh":
        return PREFIX_BROH.sub("", t).strip()
    if agent == "supp":
        return PREFIX_SUPP.sub("", t).strip()
    if agent == "intel":
        return PREFIX_INTEL.sub("", t).strip()
    if agent == "jobs":
        return PREFIX_JOBS.sub("", t).strip()
    if agent == "hlgo":
        return PREFIX_HLGO.sub("", t).strip()
    if agent == "content":
        return PREFIX_CONTENT.sub("", t).strip()
    if agent == "jenki":
        return PREFIX_JENKI.sub("", t).strip()
    if agent == "pyme-chile":
        return PREFIX_PYME.sub("", t).strip()
    return t.strip()


def parse_month_from_text(text: str) -> Optional[str]:
    t = text or ""
    m = re.search(r"\b(20\d{2})[-/](\d{1,2})\b", t)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    months = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    }
    for name, num in months.items():
        if re.search(rf"\b{name}\b", t, re.I):
            return f"{date.today().year}-{num:02d}"
    return None
