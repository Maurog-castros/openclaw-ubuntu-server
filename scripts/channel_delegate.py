"""Router determinístico canal WhatsApp/Telegram → agentes (fin, care, hlgo, …)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/node/openclaw-mauro")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent

SCR = ROOT / "scripts"
if str(SCR) not in sys.path:
    sys.path.insert(0, str(SCR))

from openclaw_message_router import (
    clear_sticky_agent,
    detect_agent,
    explicit_prefix,
    parse_month_from_text,
    save_sticky_agent,
    strip_agent_prefix,
)
from channel_user_context import (
    apply_user_env,
    guest_agent_denied_message,
    resolve_user_context,
)
from whatsapp_menu import MenuOption, finish_reply, resolve_menu_choice

RUN_PY = ROOT / "scripts/run-finanzas-py.sh"
INBOUND_CANDIDATES = [
    ROOT / "data/config/media/inbound",
    Path("/home/node/.openclaw/media/inbound"),
    Path("/home/mauro/openclaw-mauro/data/config/media/inbound"),
]

CARE_RE = re.compile(r"^\s*/care\b", re.I)
BROH_RE = re.compile(r"^\s*/broh\b", re.I)
SUPP_RE = re.compile(r"^\s*/supp\b", re.I)
INTEL_RE = re.compile(r"^\s*/intel\b", re.I)
JOBS_RE = re.compile(r"^\s*/(?:jobs|postula)\b", re.I)
HLGO_RE = re.compile(r"^\s*/(?:hlgo|hl-go|hl)\b", re.I)
CONTENT_RE = re.compile(r"^\s*/content\b|instagram\.com/(?:p|reel)/", re.I)
RECENT_RECEIPTS_RE = re.compile(
    r"\b(ultim(?:as|os)|recientes|procesad(?:as|os)|historial)\b.*\b(boleta?s?|ticket?s?|recibos?)\b"
    r"|\b(boleta?s?|ticket?s?|recibos?)\b.*\b(ultim(?:as|os)|recientes|procesad(?:as|os))\b"
    r"|\bcuales?\s+(?:son\s+)?(?:las?\s+)?ultim(?:as|os)\b",
    re.I,
)
RECENT_RECEIPTS_LIMIT_RE = re.compile(r"\b(\d{1,2})\s*(?:ultim(?:as|os))?\s*boleta", re.I)
NEW_RESET_RE = re.compile(r"^\s*/(?:new|reset)\b", re.I)
HELP_CMD_RE = re.compile(r"^\s*/help\b", re.I)
STATUS_CMD_RE = re.compile(r"^\s*/status\b", re.I)
SALDO_RE = re.compile(
    r"\bsaldo\b|cuenta\s+corriente|\bsantander\b|\bdisponible\b"
    r"|este\s+es\s+mi\s+saldo|mi\s+saldo\s+es|saldo\s+real|captura|screenshot"
    r"|actualiz(?:ar|a)\s+(?:mi\s+)?saldo|dame\s+(?:el\s+)?saldo|cu[aá]nto\s+tengo",
    re.I,
)
TRANSFERENCIAS_RE = re.compile(
    r"\b(transferencias?|movimientos?\s+bancari|movimientos?\s+del\s+banco|"
    r"movimientos?\s+recientes|cartola|giros?\s+(?:salida|enviados?)|"
    r"depositos?|abonos?|cargos?\s+bancari|ultim(?:os|as)\s+movimientos?)\b",
    re.I,
)
GASTOS_RE = re.compile(
    r"\b(gastos?\s+(?:del?\s+)?mes|cu[aá]nto\s+gast[eé]|gast[eé]\s+en\s+|"
    r"resumen\s+mensual|gasto\s+total|cu[aá]nto\s+llev(?:o|amos)\s+gastado)\b",
    re.I,
)
DEDUPE_RE = re.compile(
    r"\b(duplicad|mismo\s+monto|otra\s+vez|corrige|es\s+la\s+misma|misma\s+transacc)\b",
    re.I,
)
BOLETA_RE = re.compile(
    r"\b(boleta|ticket|compra|recibo|foto|supermercado|farmacia|minimarket)\b",
    re.I,
)
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
FIN_PREFIX_RE = re.compile(r"^\s*/(?:fin|finanzas)\b\s*", re.I)
GUEST_GREETING_RE = re.compile(r"^\s*(?:hola|buenas|hey|hi|hello)\b", re.I)


def py_cmd(script: str, *args: str) -> list[str]:
    return [str(RUN_PY), str(SCR / script), *args]


def run_json(cmd: list[str], timeout: int = 200) -> tuple[int, dict, str, str]:
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout, check=False)
    payload: dict = {}
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"whatsapp_reply": proc.stdout.strip()}
    return proc.returncode, payload, proc.stdout, proc.stderr


def emit(payload: dict, *, as_json: bool, agent: str = "fin", skip_menu: bool = False) -> None:
    reply = payload.get("whatsapp_reply") or payload.get("summary") or ""
    if reply and payload.get("status") not in {"skip", "delegate_miss", "error"}:
        payload.setdefault("status", "ok")
    if reply and payload.get("status") not in {"skip", "delegate_miss"}:
        menu_agent = payload.get("agent") or agent
        if menu_agent not in ("fin", "supp"):
            menu_agent = "fin"
        payload["whatsapp_reply"] = finish_reply(reply, agent=menu_agent, skip_menu=skip_menu)
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload.get("whatsapp_reply", ""))


def strip_fin_prefix(text: str) -> str:
    return FIN_PREFIX_RE.sub("", text or "").strip()


def resolve_inbound() -> Path:
    import os

    user_inbound = os.environ.get("OPENCLAW_USER_INBOUND_DIR", "").strip()
    if user_inbound:
        return Path(user_inbound)
    for candidate in INBOUND_CANDIDATES:
        if candidate.exists():
            return candidate
    return INBOUND_CANDIDATES[0]


def latest_inbound_image(max_age_sec: int = 120) -> Path | None:
    inbound = resolve_inbound()
    if not inbound.exists():
        return None
    now = time.time()
    candidates = [
        p
        for p in inbound.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXT and (now - p.stat().st_mtime) <= max_age_sec
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def run_script_menu(value: str) -> dict:
    parts = value.split("|")
    script = parts[0]
    args = parts[1:] if len(parts) > 1 else []
    code, payload, _, stderr = run_json(py_cmd(script, *args, "--json"))
    if code != 0 and not payload.get("whatsapp_reply") and not payload.get("summary"):
        return {"status": "error", "agent": "fin", "whatsapp_reply": stderr[:400] or "Error ejecutando accion."}
    payload.setdefault("agent", "fin")
    payload.setdefault("status", "ok")
    payload.setdefault("whatsapp_reply", payload.get("summary") or "")
    return payload


def run_menu_option(opt: MenuOption) -> dict:
    if opt.kind == "text":
        if opt.key == "1" or "saldo" in (opt.label or "").lower():
            return run_saldo(opt.value, None, amount=None, report_only=True, short=True)
        return dispatch_text(opt.value, has_media=False, image_path=None, amount=0)
    if opt.kind == "script":
        return run_script_menu(opt.value)
    if opt.kind == "monthly":
        code, payload, _, stderr = run_json(
            py_cmd("finanzas_monthly_report.py", "--month", opt.value, "--json")
        )
        if code != 0:
            return {"status": "error", "agent": "fin", "whatsapp_reply": stderr[:400] or "Sin reporte mensual."}
        payload.setdefault("whatsapp_reply", payload.get("summary") or "")
        payload.setdefault("agent", "fin")
        return payload
    if opt.kind == "supp":
        code, payload, _, stderr = run_json(
            py_cmd("support_delegate.py", "--text", f"/supp {opt.value}", "--json")
        )
        payload.setdefault("agent", "supp")
        if code != 0 and not payload.get("whatsapp_reply"):
            payload["whatsapp_reply"] = stderr[:400] or "Supp no respondio."
        return payload
    return {"status": "error", "agent": "fin", "whatsapp_reply": "Opcion de menu desconocida."}


def should_process_dedupe(text: str) -> bool:
    if not DEDUPE_RE.search(text or ""):
        return False
    t = text or ""
    if re.search(r"\$\s*\d{1,3}(?:\.\d{3})+|\d{5,}", t):
        return True
    if re.search(r"\b(TRANSF|RENOVAL|arriendo)\b", t, re.I):
        return True
    return False


def run_dedupe(text: str) -> dict:
    code, payload, _, stderr = run_json(py_cmd("finanzas_dedupe_movimientos.py", "auto-link", "--text", text, "--json"))
    if code != 0 and not payload.get("whatsapp_reply"):
        return {
            "status": "error",
            "agent": "fin",
            "whatsapp_reply": "No pude vincular duplicados. Indica monto y nombre (ej. RENOVAL).",
            "stderr": stderr[-800:],
        }
    payload.setdefault("agent", "fin")
    payload.setdefault("status", payload.get("status", "ok"))
    return payload


def should_process_saldo(text: str, has_media: bool, image_path: str | None) -> bool:
    t = (text or "").strip()
    if SALDO_RE.search(t):
        return True
    try:
        from finanzas_saldo import parse_balance_text

        if parse_balance_text(t):
            return True
    except ImportError:
        pass
    return False


def should_process_receipt(text: str, has_media: bool, image_path: str | None) -> bool:
    if NEW_RESET_RE.search(text) or HELP_CMD_RE.search(text) or STATUS_CMD_RE.search(text):
        return False
    if RECENT_RECEIPTS_RE.search(text):
        return False
    if should_process_saldo(text, has_media, image_path):
        return False
    if BOLETA_RE.search(text):
        return True
    if has_media or image_path:
        latest = latest_inbound_image()
        if not image_path and not latest:
            return False
        t = (text or "").strip()
        if len(t) >= 140:
            return False
        if SALDO_RE.search(t):
            return False
        return bool(BOLETA_RE.search(t) or len(t) < 80)
    if latest_inbound_image():
        return bool(BOLETA_RE.search(text) or len((text or "").strip()) < 80)
    return False


def parse_recent_receipts_limit(text: str, default: int = 10) -> int:
    m = RECENT_RECEIPTS_LIMIT_RE.search(text or "")
    if m:
        return max(1, min(int(m.group(1)), 20))
    m2 = re.search(r"\b(\d{1,2})\s+boleta", text or "", re.I)
    if m2:
        return max(1, min(int(m2.group(1)), 20))
    return default


def run_session_reset() -> dict:
    try:
        from support_common import clear_whatsapp_pending_and_reset_sessions, live_health

        clear_whatsapp_pending_and_reset_sessions(restart_gateway=True)
        health = live_health()
        pending = health.get("whatsapp_pending", 0)
        sess = (health.get("fin_session") or {}).get("status") or "nueva"
    except ImportError:
        pending = "?"
        sess = "?"
    reply = (
        "Sesion reiniciada.\n"
        f"WhatsApp pending: {pending}\n"
        f"Sesion fin: {sess}\n"
        "Escribe /fin o tu consulta de nuevo.\n"
        "Hilo de agente reiniciado."
    )
    return {"status": "ok", "agent": "fin", "whatsapp_reply": reply}


def run_help() -> dict:
    import os

    if os.environ.get("OPENCLAW_USER_IS_OWNER") != "1":
        name = os.environ.get("OPENCLAW_USER_NAME", "tu espacio")
        text = (
            f"Hola, *{name}*. Este es tu asistente personal (datos separados).\n\n"
            "Escribe en lenguaje natural o usa:\n"
            "• /fin — saldo, gastos, boletas, transferencias\n"
            "• /care — diario, ánimo, salud\n"
            "• Menú 1-4 al final de cada respuesta\n"
            "• /new — reiniciar conversación\n"
            "• /help — esta ayuda"
        )
    else:
        text = (
            "Sin prefijo: intencion automatica o continuar el hilo del ultimo /agent.\n"
            "Prefijos: /fin /care /broh /supp /intel /jobs /hlgo /content\n"
            "Tras /care (u otro), los mensajes siguientes van al mismo agente hasta /new, /reset u otro prefijo.\n"
            "/fin saldo — saldo Santander\n"
            "/fin ultimas boletas — listado\n"
            "/new o /reset — sesion limpia\n"
            "Foto + texto — registrar boleta o saldo Santander"
        )
    return {"status": "ok", "agent": "fin", "whatsapp_reply": text}


def run_status_cmd() -> dict:
    try:
        from support_common import live_health

        health = live_health()
        lines = [
            "Estado /fin:",
            f"Gateway: {'OK' if health.get('gateway_healthy') else 'NO'}",
            f"WhatsApp pending: {health.get('whatsapp_pending', 0)}",
            f"Sesion: {(health.get('fin_session') or {}).get('status', '?')}",
            f"Entregas failed: {health.get('fin_failed_deliveries', 0)}",
        ]
        if health.get("needs_remediation"):
            lines.append("Usa /supp fix o menu 5.")
        return {"status": "ok", "agent": "fin", "whatsapp_reply": "\n".join(lines)}
    except ImportError:
        return run_saldo("como va mi saldo", None, None)


def run_transferencias(text: str, limit: int = 5) -> dict:
    m = re.search(r"\b(\d{1,2})\s*(?:ultim(?:os|as))?\s*(?:movimientos?|transferencias?)\b", text or "", re.I)
    if m:
        limit = max(1, min(int(m.group(1)), 20))
    code, payload, _, stderr = run_json(
        py_cmd("finanzas_transferencias_report.py", "--limit", str(limit), "--json")
    )
    if code != 0 and not payload.get("whatsapp_reply"):
        return {
            "status": "error",
            "agent": "fin",
            "whatsapp_reply": "No pude listar movimientos bancarios.",
            "stderr": stderr[-800:],
        }
    payload.setdefault("agent", "fin")
    payload.setdefault("status", "ok")
    payload.setdefault("whatsapp_reply", payload.get("summary") or "")
    return payload


def run_monthly_gastos(text: str) -> dict:
    from datetime import date

    month = parse_month_from_text(text) or date.today().strftime("%Y-%m")
    code, payload, _, stderr = run_json(py_cmd("finanzas_monthly_report.py", "--month", month, "--json"))
    if code != 0 and not payload.get("whatsapp_reply"):
        return {
            "status": "error",
            "agent": "fin",
            "whatsapp_reply": f"No pude generar gastos de {month}.",
            "stderr": stderr[-800:],
        }
    payload.setdefault("agent", "fin")
    payload.setdefault("status", "ok")
    payload.setdefault("whatsapp_reply", payload.get("summary") or "")
    return payload


def run_care_delegate(raw_text: str, has_media: bool, image_path: str | None) -> dict:
    care_text = raw_text if CARE_RE.search(raw_text) else f"/care {raw_text}"
    care_cmd = py_cmd("vida_delegate.py", "--text", care_text, "--json")
    if has_media:
        care_cmd.append("--has-media")
    if image_path:
        care_cmd.extend(["--image", image_path])
    code, payload, _, _ = run_json(care_cmd, timeout=240)
    payload.setdefault("agent", "care")
    if code != 0 and not payload.get("whatsapp_reply"):
        payload["whatsapp_reply"] = "Care no respondio."
        payload["status"] = "error"
    elif payload.get("whatsapp_reply"):
        payload.setdefault("status", "ok")
    return payload


def run_broh_delegate(raw_text: str) -> dict:
    broh_text = raw_text if BROH_RE.search(raw_text) else f"/broh {raw_text}"
    code, payload, _, stderr = run_json(py_cmd("broh_delegate.py", "--text", broh_text, "--json"), timeout=180)
    if code != 0 and not payload.get("whatsapp_reply"):
        payload = {
            "status": "error",
            "agent": "broh",
            "whatsapp_reply": "Broh no respondio.",
            "stderr": stderr[-800:],
        }
    payload.setdefault("agent", "broh")
    return payload


def run_supp_delegate(raw_text: str) -> dict:
    supp_text = raw_text if SUPP_RE.search(raw_text) else f"/supp {raw_text}"
    code, payload, _, stderr = run_json(py_cmd("support_delegate.py", "--text", supp_text, "--json"))
    if code != 0 and not payload.get("whatsapp_reply"):
        payload = {"status": "error", "agent": "supp", "whatsapp_reply": "Supp no respondio.", "stderr": stderr[-800:]}
    payload.setdefault("agent", "supp")
    return payload


def run_intel_delegate(text: str) -> dict:
    intel_text = text if INTEL_RE.search(text) else f"/intel {text}"
    code, payload, _, stderr = run_json(py_cmd("intel_delegate.py", "--text", intel_text, "--json"))
    if code != 0 and not payload.get("whatsapp_reply"):
        payload = {"status": "error", "agent": "intel", "whatsapp_reply": "Intel no respondio.", "stderr": stderr[-800:]}
    payload.setdefault("agent", "intel")
    return payload


def run_jobs_delegate(text: str) -> dict:
    jobs_text = text if JOBS_RE.search(text) else f"/jobs {text}"
    code, payload, _, stderr = run_json(py_cmd("jobs_delegate.py", "--text", jobs_text, "--json"), timeout=300)
    if code != 0 and not payload.get("whatsapp_reply"):
        payload = {"status": "error", "agent": "jobs", "whatsapp_reply": "Jobs no respondio.", "stderr": stderr[-800:]}
    payload.setdefault("agent", "jobs")
    return payload


def run_hlgo_delegate(text: str) -> dict:
    hl_text = text if HLGO_RE.search(text) else f"/hl {text}"
    code, payload, _, stderr = run_json(py_cmd("hl_go_delegate.py", "--text", hl_text, "--json"), timeout=300)
    if code != 0 and not payload.get("whatsapp_reply"):
        payload = {"status": "error", "agent": "hlgo", "whatsapp_reply": "HL-Go no respondio.", "stderr": stderr[-800:]}
    payload.setdefault("agent", "hlgo")
    return payload


def run_content_delegate(text: str) -> dict:
    code, payload, _, _ = run_json(py_cmd("content_instagram_whatsapp.py", "--text", text, "--json"))
    if code != 0 and not payload.get("whatsapp_reply"):
        payload = {
            "status": "error",
            "agent": "content",
            "whatsapp_reply": payload.get("message", "Content no respondio."),
        }
    payload.setdefault("agent", "content")
    return payload


def run_recent_receipts(limit: int = 10) -> dict:
    code, payload, _, stderr = run_json(py_cmd("finanzas_recent_receipts.py", "--limit", str(limit), "--json"))
    if code != 0 and not payload.get("whatsapp_reply"):
        return {"status": "error", "agent": "fin", "whatsapp_reply": "No pude listar boletas recientes.", "stderr": stderr[-800:]}
    payload.setdefault("agent", "fin")
    payload.setdefault("status", "ok")
    return payload


def run_saldo(
    text: str,
    image_path: str | None,
    amount: int | None = None,
    *,
    report_only: bool = False,
    short: bool = False,
) -> dict:
    cmd = py_cmd("finanzas_saldo_whatsapp.py", "--text", text, "--json")
    if amount is not None and amount > 0:
        cmd.extend(["--amount", str(amount)])
    elif report_only:
        cmd.append("--report-only")
    else:
        try:
            from finanzas_saldo import wants_set_actual

            if not wants_set_actual(text, has_image=bool(image_path)):
                cmd.append("--report-only")
        except ImportError:
            pass
    if short:
        cmd.append("--short")
    if image_path:
        cmd.extend(["--image", image_path])
    code, payload, _, stderr = run_json(cmd, timeout=120)
    if code != 0 and not payload.get("whatsapp_reply"):
        return {
            "status": "error",
            "agent": "fin",
            "whatsapp_reply": "No pude procesar el saldo. Intenta con el monto en texto.",
            "stderr": stderr[-800:],
        }
    payload.setdefault("agent", "fin")
    payload.setdefault("status", payload.get("status", "ok"))
    return payload


def run_receipt(text: str, source: str, image_path: str | None) -> dict:
    inbound = resolve_inbound()
    cmd = py_cmd(
        "finanzas_receipt_whatsapp.py",
        "--text",
        text,
        "--inbound-dir",
        str(inbound),
        "--source",
        source,
        "--json",
    )
    if image_path:
        cmd.extend(["--image", image_path])
    code, payload, stdout, stderr = run_json(cmd, timeout=200)
    if code != 0 and not payload.get("whatsapp_reply"):
        return {
            "status": "error",
            "agent": "finanzas",
            "whatsapp_reply": "No pude procesar la boleta. Revisa logs del gateway.",
            "stderr": stderr[-1000:],
            "stdout": stdout[-1000:],
        }
    payload.setdefault("agent", "finanzas")
    payload.setdefault("status", payload.get("status", "ok"))
    return payload


def dispatch_text(
    text: str,
    *,
    has_media: bool,
    image_path: str | None,
    amount: int,
    raw_text: str = "",
) -> dict:
    if SUPP_RE.search(raw_text or ""):
        code, payload, _, stderr = run_json(py_cmd("support_delegate.py", "--text", raw_text or "", "--json"))
        if code != 0 and not payload.get("whatsapp_reply"):
            payload = {"status": "error", "agent": "supp", "whatsapp_reply": "Supp no respondio.", "stderr": stderr[-800:]}
        payload.setdefault("agent", "supp")
        return payload

    if INTEL_RE.search(text):
        code, payload, _, stderr = run_json(py_cmd("intel_delegate.py", "--text", text, "--json"))
        if code != 0 and not payload.get("whatsapp_reply"):
            payload = {"status": "error", "whatsapp_reply": "Intel no respondio.", "stderr": stderr[-800:]}
        payload.setdefault("agent", "fin")
        return payload

    if CONTENT_RE.search(text):
        code, payload, _, _ = run_json(py_cmd("content_instagram_whatsapp.py", "--text", text, "--json"))
        if code != 0 and not payload.get("whatsapp_reply"):
            payload = {"status": "error", "whatsapp_reply": payload.get("message", "Content no respondio.")}
        payload.setdefault("agent", "fin")
        return payload

    if RECENT_RECEIPTS_RE.search(text):
        return run_recent_receipts(parse_recent_receipts_limit(text))

    try:
        from finanzas_transfer_whatsapp import looks_like_transfer_email, process_transfer_email

        if looks_like_transfer_email(text):
            result = process_transfer_email(text)
            if result.get("status") != "skip":
                result.setdefault("agent", "fin")
                return result
    except ImportError:
        pass

    if TRANSFERENCIAS_RE.search(text):
        return run_transferencias(text)

    if GASTOS_RE.search(text):
        return run_monthly_gastos(text)

    if should_process_dedupe(text):
        return run_dedupe(text)

    if amount and amount > 0:
        return run_saldo(text, image_path, amount=amount)

    if should_process_saldo(text, has_media, image_path):
        img = image_path
        is_media = has_media or bool(img)
        try:
            from finanzas_saldo import wants_set_actual

            set_mode = wants_set_actual(
                text, has_image=is_media, explicit_amount=bool(amount and amount > 0)
            )
        except ImportError:
            set_mode = is_media
        return run_saldo(
            text,
            img,
            amount=amount if amount else None,
            report_only=not set_mode and not (amount and amount > 0),
            short=not set_mode,
        )

    if should_process_receipt(text, has_media, image_path):
        return run_receipt(text, "whatsapp_foto", image_path)

    return {"status": "delegate_miss", "agent": "finanzas", "whatsapp_reply": ""}


def run_guest_welcome(user_ctx) -> dict:
    name = user_ctx.display_name or "amigo"
    return {
        "status": "ok",
        "agent": "fin",
        "whatsapp_reply": (
            f"Hola, *{name}*. Este es tu asistente personal (datos solo tuyos).\n\n"
            "Prueba:\n"
            "• *1* — ver saldo\n"
            "• *4* — últimas boletas\n"
            "• */care* — diario y ánimo\n"
            "• */help* — más opciones"
        ),
    }


def _deny_agent(agent: str, user_ctx) -> dict | None:
    if user_ctx.allows(agent):
        return None
    return {
        "status": "ok",
        "agent": "fin",
        "whatsapp_reply": guest_agent_denied_message(agent),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Router canal WhatsApp/Telegram (multi-agente).")
    parser.add_argument("--text", default="")
    parser.add_argument("--amount", type=int, default=0)
    parser.add_argument("--has-media", action="store_true")
    parser.add_argument("--image", default=None)
    parser.add_argument("--source", default="whatsapp_foto")
    parser.add_argument("--peer", default="", help="E.164 remitente WhatsApp (+569...)")
    parser.add_argument("--session-key", default="", help="sessionKey OpenClaw")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    user_ctx = resolve_user_context(peer=args.peer, session_key=args.session_key)
    apply_user_env(user_ctx)

    raw_text = (args.text or "").strip()
    image_path = args.image or (str(latest_inbound_image()) if args.has_media else None)
    has_media = args.has_media or bool(image_path)

    if NEW_RESET_RE.search(raw_text):
        clear_sticky_agent()
        emit(run_session_reset(), as_json=args.json)
        return

    if CARE_RE.search(raw_text):
        denied = _deny_agent("care", user_ctx)
        if denied:
            emit(denied, as_json=args.json, agent="care", skip_menu=True)
            return
        save_sticky_agent("care")
        emit(run_care_delegate(raw_text, has_media, image_path), as_json=args.json, agent="care", skip_menu=True)
        return

    if BROH_RE.search(raw_text):
        denied = _deny_agent("broh", user_ctx)
        if denied:
            emit(denied, as_json=args.json, agent="broh", skip_menu=True)
            return
        save_sticky_agent("broh")
        emit(run_broh_delegate(raw_text), as_json=args.json, agent="broh", skip_menu=True)
        return

    text = strip_fin_prefix(raw_text)
    if HELP_CMD_RE.search(text):
        emit(run_help(), as_json=args.json)
        return
    if GUEST_GREETING_RE.match(text) and not user_ctx.is_owner:
        emit(run_guest_welcome(user_ctx), as_json=args.json)
        return
    if STATUS_CMD_RE.search(text):
        emit(run_status_cmd(), as_json=args.json)
        return

    menu_opt = resolve_menu_choice(text)
    if menu_opt:
        emit(run_menu_option(menu_opt), as_json=args.json)
        return

    agent = detect_agent(raw_text, has_media=has_media)
    denied = _deny_agent(agent, user_ctx)
    if denied:
        emit(denied, as_json=args.json, agent="fin", skip_menu=True)
        return
    if agent == "care":
        emit(run_care_delegate(raw_text, has_media, image_path), as_json=args.json, agent="care", skip_menu=True)
        return
    if agent == "broh":
        emit(run_broh_delegate(raw_text), as_json=args.json, agent="broh", skip_menu=True)
        return
    if agent == "supp":
        emit(run_supp_delegate(raw_text), as_json=args.json, agent="supp")
        return
    if agent == "intel":
        emit(
            run_intel_delegate(strip_agent_prefix(raw_text, "intel") or raw_text),
            as_json=args.json,
            agent="fin",
            skip_menu=True,
        )
        return
    if agent == "jobs":
        emit(
            run_jobs_delegate(strip_agent_prefix(raw_text, "jobs") or raw_text),
            as_json=args.json,
            agent="fin",
            skip_menu=True,
        )
        return
    if agent == "hlgo":
        result = run_hlgo_delegate(strip_agent_prefix(raw_text, "hlgo") or raw_text)
        if result.get("whatsapp_reply") and result.get("status") not in {"skip", "delegate_miss"}:
            result.setdefault("status", "ok")
        emit(result, as_json=args.json, agent="fin", skip_menu=True)
        return
    if agent == "content":
        emit(
            run_content_delegate(strip_agent_prefix(raw_text, "content") or raw_text),
            as_json=args.json,
            agent="fin",
            skip_menu=True,
        )
        return

    body = strip_agent_prefix(raw_text, "fin") if explicit_prefix(raw_text) == "fin" else text
    result = dispatch_text(
        body,
        has_media=has_media,
        image_path=image_path,
        amount=int(args.amount or 0),
        raw_text=raw_text,
    )

    if result.get("status") == "delegate_miss":
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        sys.exit(2)
        return

    emit(result, as_json=args.json)


if __name__ == "__main__":
    main()
