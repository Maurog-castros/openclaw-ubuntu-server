"""Saldo esperado Cuenta Corriente Santander vs saldo real reportado por el usuario."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import (
    DEFAULT_CARTOLA_CSV,
    DEFAULT_SALDO_STATE,
    DEFAULT_UNIFIED_CSV,
    normalize_store_name,
    parse_clp,
    read_csv_rows,
    resolve_data_path,
)
from finanzas_merchant_report import fmt_clp, load_all_rows, parse_iso_date

BANK_SOURCES = frozenset({"santander_cartola", "santander_gmail"})
RECEIPT_SOURCES = frozenset(
    {"lider_gmail", "telegram_foto", "whatsapp_foto", "openclaw_web", "manual"}
)
# Perfil Mauricio: ~95% pago digital. "desconocido" en boleta = tarjeta/debito.
DEBIT_PAYMENT = frozenset({"", "desconocido", "tarjeta", "transferencia", "debito", "débito", "digital"})
CASH_PAYMENT = frozenset({"efectivo", "cash"})
DIFF_TOLERANCE_CLP = 500
BANK_MATCH_WINDOW_DAYS = 5
PENDING_MAX_AGE_DAYS = 7
DEFAULT_PAYMENT_PROFILE = "digital"

BALANCE_TEXT_RE = re.compile(
    r"(?:saldo|tengo|disponible|cuenta)[^\d$]{0,40}(\d{1,3}(?:\.\d{3})+|\d{4,})",
    re.IGNORECASE,
)
# Monto con $ (CLP chileno: $103.699). Debe ir antes de PLAIN_AMOUNT.
CLP_DOLLAR_RE = re.compile(
    r"\$\s*(\d{1,3}(?:\.\d{3})+|\d{4,})",
    re.IGNORECASE,
)
PLAIN_AMOUNT_RE = re.compile(r"\b(\d{1,3}(?:\.\d{3})+)\b")
# Bash expande $103.699 como $1 + "03.699" -> queda "03.699" (3699 CLP).
BASH_TRUNCATED_SALDO_RE = re.compile(
    r"(?:saldo|disponible|tengo|cuenta|real)[^\d]{0,40}(0\d\.\d{3})\b",
    re.IGNORECASE,
)
# Solo actualizar ancla si el usuario reporta saldo nuevo (no consultas tipo menu 1).
SET_ACTUAL_INTENT_RE = re.compile(
    r"mi\s+saldo\s+es|este\s+es\s+mi\s+saldo|actualiz|registr|ancla|"
    r"tengo\s+\$|saldo\s+(?:de\s+)?(?:hoy|ahora)|screenshot|captura|"
    r"en\s+(?:la\s+)?app|desde\s+(?:la\s+)?app",
    re.IGNORECASE,
)


def wants_set_actual(text: str, *, has_image: bool = False, explicit_amount: bool = False) -> bool:
    """True si el usuario quiere guardar un saldo nuevo, no solo consultarlo."""
    if explicit_amount:
        return True
    if has_image:
        return True
    t = (text or "").strip()
    if not t:
        return False
    if SET_ACTUAL_INTENT_RE.search(t):
        if parse_balance_text(t):
            return True
        # "actualizar mi saldo" sin monto en texto: OCR en screenshot o error claro.
        return bool(re.search(r"actualiz|ancla|registr", t, re.I))
    return False


def parse_balance_text(text: str) -> Optional[int]:
    if not text:
        return None
    dollar_match = CLP_DOLLAR_RE.search(text)
    if dollar_match:
        amount = parse_clp(dollar_match.group(1))
        if amount and amount >= 1000:
            return amount
    trunc = BASH_TRUNCATED_SALDO_RE.search(text)
    if trunc:
        fixed = parse_clp("1" + trunc.group(1))
        if fixed and fixed >= 10_000:
            return fixed
    match = BALANCE_TEXT_RE.search(text)
    if match:
        return parse_clp(match.group(1))
    amounts = [parse_clp(m.group(1)) for m in PLAIN_AMOUNT_RE.finditer(text)]
    amounts = [a for a in amounts if a and a >= 1000]
    if len(amounts) == 1:
        return amounts[0]
    if amounts:
        return max(amounts)
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 4:
        return int(digits)
    return None


def load_saldo_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"anchors": [], "last_actual": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"anchors": [], "last_actual": None}
    if not isinstance(data, dict):
        return {"anchors": [], "last_actual": None}
    data.setdefault("anchors", [])
    data.setdefault("payment_profile", DEFAULT_PAYMENT_PROFILE)
    return data


def save_saldo_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def last_cartola_balance(cartola_csv: Path) -> Optional[Dict[str, Any]]:
    """Ultimo saldo confiable en cartola (filtra montos OCR erroneos pequenos)."""
    best: Optional[Dict[str, Any]] = None
    for row in read_csv_rows(cartola_csv):
        balance = parse_clp(row.get("balance_clp"))
        movement_date = row.get("movement_date") or ""
        if balance is None or balance < 10_000 or not movement_date:
            continue
        if best is None or movement_date >= best.get("as_of_date", ""):
            best = {
                "balance_clp": balance,
                "as_of_date": movement_date,
                "as_of_datetime": f"{movement_date} 23:59:59",
                "source": "santander_cartola",
                "notes": f"Ultimo saldo cartola ({row.get('description') or 'movimiento'})",
            }
    return best


def payment_profile(state: Dict[str, Any]) -> str:
    profile = str(state.get("payment_profile") or DEFAULT_PAYMENT_PROFILE).lower()
    return profile if profile in {"digital", "mixed"} else DEFAULT_PAYMENT_PROFILE


def collect_bank_ledger(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Todos los cargos/abonos bancarios para conciliar boletas (fecha flexible)."""
    ledger: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("source") not in BANK_SOURCES:
            continue
        amount = int(parse_clp(row.get("amount_clp") or row.get("ticket_total") or "0") or 0)
        if amount <= 0:
            continue
        mt = (row.get("movement_type") or "").lower()
        direction = "abono" if mt in {"transferencia_entrada", "ingreso"} else "cargo"
        movement_date = parse_iso_date((row.get("movement_date") or "")[:10])
        if not movement_date:
            continue
        desc = normalize_store_name(
            row.get("description") or row.get("merchant") or row.get("counterparty") or ""
        )
        ledger.append(
            {
                "date": movement_date,
                "amount": amount,
                "direction": direction,
                "description": desc,
            }
        )
    return ledger


def bank_covers_receipt(
    receipt_date: str,
    amount: int,
    merchant: str,
    ledger: List[Dict[str, Any]],
    *,
    window_days: int = BANK_MATCH_WINDOW_DAYS,
) -> bool:
    """Mismo monto en banco dentro de ±window_days (pago digital ya descontado)."""
    rd = parse_iso_date(receipt_date[:10])
    if not rd or amount <= 0:
        return False
    merchant_norm = normalize_store_name(merchant)
    for entry in ledger:
        if entry["direction"] != "cargo" or entry["amount"] != amount:
            continue
        if abs((entry["date"] - rd).days) > window_days:
            continue
        bank_desc = entry.get("description") or ""
        if merchant_norm and len(merchant_norm) >= 4:
            if merchant_norm in bank_desc or bank_desc in merchant_norm:
                return True
            # Lider / supermercado suele aparecer como "compra lider/hiper" en cartola
            if merchant_norm == "lider" and any(
                token in bank_desc for token in ("lider", "hiper", "supermercado", "jumbo")
            ):
                return True
        else:
            return True
    return False


def active_anchor(state: Dict[str, Any], cartola_csv: Path) -> Dict[str, Any]:
    last_actual = state.get("last_actual")
    if isinstance(last_actual, dict) and last_actual.get("balance_clp"):
        return last_actual
    anchors = state.get("anchors") or []
    if anchors:
        return anchors[-1]
    cartola = last_cartola_balance(cartola_csv)
    if cartola:
        return cartola
    return {
        "balance_clp": 0,
        "as_of_date": "",
        "as_of_datetime": "",
        "source": "none",
        "notes": "Sin ancla. Reporta tu saldo real con: finanzas_saldo.py set-actual --amount N",
    }


def _after_anchor(row: Dict[str, str], anchor_date: str, *, inclusive: bool = False) -> bool:
    movement_date = (row.get("movement_date") or "")[:10]
    if not movement_date or not anchor_date:
        return bool(movement_date)
    if inclusive:
        return movement_date >= anchor_date
    return movement_date > anchor_date


def receipt_key(row: Dict[str, str]) -> Tuple[str, str, int]:
    total = int(parse_clp(row.get("ticket_total") or row.get("amount_clp") or "0") or 0)
    return (
        (row.get("movement_date") or "")[:10],
        (row.get("merchant") or "").strip().lower(),
        total,
    )


def pending_receipt_debits(
    rows: List[Dict[str, str]],
    anchor_date: str,
    ledger: List[Dict[str, Any]],
    *,
    profile: str,
    anchor_source: str = "",
) -> List[Dict[str, Any]]:
    """
    Boletas digitales aun no visibles en banco.
    Perfil digital: solo ultimos PENDING_MAX_AGE_DAYS y sin match banco (±window).
    Si ancla es saldo real del usuario, no descontar boletas del mismo dia (ya incluidas).
    """
    if profile == "digital":
        max_age = PENDING_MAX_AGE_DAYS
    else:
        max_age = 30

    user_anchor = anchor_source in {"user_manual", "user_screenshot"}
    receipt_after_anchor = (
        (lambda row: _after_anchor(row, anchor_date, inclusive=False))
        if user_anchor
        else (lambda row: _after_anchor(row, anchor_date, inclusive=True))
    )

    today = date.today()
    anchor_d = parse_iso_date(anchor_date[:10]) if anchor_date else None
    seen: Set[Tuple[str, str, int]] = set()
    pending: List[Dict[str, Any]] = []

    for row in rows:
        if row.get("source") not in RECEIPT_SOURCES:
            continue
        if (row.get("movement_type") or "") != "gasto":
            continue
        if not receipt_after_anchor(row):
            continue

        pm = (row.get("payment_method") or "").lower()
        if pm in CASH_PAYMENT:
            continue
        if profile == "digital":
            # 95% digital: desconocido = debito cuenta/tarjeta
            if pm and pm not in DEBIT_PAYMENT:
                continue
        elif pm not in DEBIT_PAYMENT and pm:
            continue

        key = receipt_key(row)
        if key in seen:
            continue
        seen.add(key)
        date_s, merchant, total = key
        if total <= 0:
            continue

        rd = parse_iso_date(date_s)
        if rd:
            if (today - rd).days > max_age:
                continue
            if anchor_d and rd < anchor_d:
                continue

        if bank_covers_receipt(date_s, total, merchant, ledger):
            continue

        pending.append(
            {
                "date": date_s,
                "merchant": row.get("merchant") or "",
                "amount": total,
                "source": row.get("source") or "",
                "payment_method": row.get("payment_method") or "digital",
            }
        )
    return pending


def net_bank_movement(row: Dict[str, str]) -> int:
    amount = int(parse_clp(row.get("amount_clp") or row.get("ticket_total") or "0") or 0)
    if amount <= 0:
        return 0
    mt = (row.get("movement_type") or "").lower()
    if mt in {"transferencia_entrada", "ingreso"}:
        return amount
    if mt in {"transferencia_salida", "gasto"}:
        return -amount
    return 0


def compute_expected(
    *,
    unified_csv: Path,
    cartola_csv: Path,
    state: Dict[str, Any],
) -> Dict[str, Any]:
    anchor = active_anchor(state, cartola_csv)
    anchor_balance = int(anchor.get("balance_clp") or 0)
    anchor_date = (anchor.get("as_of_date") or "")[:10]
    profile = payment_profile(state)

    rows = load_all_rows(unified_csv)
    ledger = collect_bank_ledger(rows)

    bank_net = 0
    bank_credits = 0
    bank_debits = 0
    bank_count = 0
    for row in rows:
        if row.get("source") not in BANK_SOURCES:
            continue
        if not _after_anchor(row, anchor_date):
            continue
        delta = net_bank_movement(row)
        if delta == 0:
            continue
        bank_net += delta
        if delta > 0:
            bank_credits += delta
        else:
            bank_debits += abs(delta)
        bank_count += 1

    pending = pending_receipt_debits(
        rows,
        anchor_date,
        ledger,
        profile=profile,
        anchor_source=str(anchor.get("source") or ""),
    )
    pending_total = sum(item["amount"] for item in pending)

    expected = anchor_balance + bank_net - pending_total

    return {
        "anchor": anchor,
        "payment_profile": profile,
        "expected_balance_clp": expected,
        "components": {
            "anchor_balance_clp": anchor_balance,
            "bank_net_clp": bank_net,
            "bank_credits_clp": bank_credits,
            "bank_debits_clp": bank_debits,
            "bank_movements_count": bank_count,
            "pending_receipts_clp": pending_total,
            "pending_receipts_count": len(pending),
        },
        "pending_receipts": pending[:15],
    }


def explain_difference(
    expected: int,
    actual: int,
    report: Dict[str, Any],
) -> List[str]:
    diff = actual - expected
    causes: List[str] = []
    if abs(diff) <= DIFF_TOLERANCE_CLP:
        return ["Saldo cuadrado (pago digital + ancla al dia)."]

    profile = report.get("payment_profile") or DEFAULT_PAYMENT_PROFILE
    anchor = report.get("anchor") or {}
    anchor_date = anchor.get("as_of_date") or ""
    if anchor_date:
        try:
            days = (date.today() - date.fromisoformat(anchor_date)).days
            if days > 3:
                causes.append(
                    f"Ancla de saldo hace {days} dias ({anchor_date}): recalibra con screenshot "
                    "app Santander para cuadrar (pago digital deberia coincidir)."
                )
        except ValueError:
            pass

    pending = report.get("pending_receipts") or []
    pending_total = int((report.get("components") or {}).get("pending_receipts_clp") or 0)

    if diff < 0:
        causes.append(
            f"Saldo real ${abs(diff):,} menor al esperado.".replace(",", ".")
        )
        if pending:
            causes.append(
                f"Compras digitales recientes (${pending_total:,}) aun no reflejadas en "
                "transferencias Gmail/cartola (normal 1-3 dias).".replace(",", ".")
            )
        causes.append(
            "Revisa: transferencia saliente sin comprobante Gmail, comision banco, "
            "o compra tarjeta debito del dia que aun no sincroniza."
        )
    else:
        causes.append(
            f"Saldo real ${diff:,} mayor al esperado.".replace(",", ".")
        )
        causes.append(
            "Revisa: abono/transferencia entrante o devolucion aun no en finanzas."
        )

    if profile == "digital":
        causes.append(
            "Perfil digital: casi todo deberia cuadrar si recalibras saldo desde la app "
            "al menos cada pocos dias."
        )
    return causes


def format_summary(report: Dict[str, Any], *, actual: Optional[int] = None) -> str:
    expected = int(report.get("expected_balance_clp") or 0)
    anchor = report.get("anchor") or {}
    comp = report.get("components") or {}

    lines = [
        "Saldo Cuenta Corriente Santander (calculado):",
        f"Saldo esperado: {fmt_clp(expected)}",
    ]
    anchor_bal = int(anchor.get("balance_clp") or 0)
    anchor_date = anchor.get("as_of_date") or "?"
    anchor_src = anchor.get("source") or "?"
    lines.append(f"Base: {fmt_clp(anchor_bal)} al {anchor_date} ({anchor_src})")

    if comp.get("bank_movements_count"):
        lines.append(
            f"Mov. banco desde ancla: -{fmt_clp(comp.get('bank_debits_clp', 0))} / "
            f"+{fmt_clp(comp.get('bank_credits_clp', 0))}"
        )
    pending_n = comp.get("pending_receipts_count") or 0
    if pending_n:
        lines.append(
            f"Boletas debito pendientes banco: -{fmt_clp(comp.get('pending_receipts_clp', 0))} ({pending_n})"
        )

    if actual is not None:
        diff = actual - expected
        lines.append(f"Saldo real (tu reporte): {fmt_clp(actual)}")
        if abs(diff) <= DIFF_TOLERANCE_CLP:
            lines.append("Estado: cuadrado")
        else:
            sign = "+" if diff > 0 else "-"
            lines.append(f"Diferencia: {sign}{fmt_clp(abs(diff))}")
            lines.append("Posibles causas:")
            for cause in explain_difference(expected, actual, report):
                lines.append(f"- {cause}")

    if not anchor.get("as_of_date"):
        lines.append(
            "Tip: dime tu saldo real (ej. «tengo $1.234.567 en Santander») "
            "o envia screenshot app Santander para calibrar."
        )
    elif actual is None:
        lines.append(
            "Tip: comparte saldo real (app Santander) cada pocos dias — con pago digital deberia cuadrar."
        )

    return "\n".join(lines)


def format_short_report(report: Dict[str, Any]) -> str:
    expected = int(report.get("expected_balance_clp") or 0)
    anchor = report.get("anchor") or {}
    anchor_date = (anchor.get("as_of_date") or "")[:10]
    lines = [f"Saldo Santander actual: {fmt_clp(expected)}"]
    if anchor_date:
        lines.append(f"Ancla: {anchor_date}")
    return "\n".join(lines)


def format_set_actual_reply(amount: int, entry: Dict[str, Any]) -> str:
    src_labels = {
        "user_screenshot": "screenshot app Santander",
        "user_manual": "tu mensaje",
    }
    src = src_labels.get(str(entry.get("source") or ""), entry.get("source") or "usuario")
    when = entry.get("as_of_date") or "?"
    return (
        f"Saldo Santander actualizado: {fmt_clp(amount)}\n"
        f"Fecha ancla: {when} ({src})\n"
        f"Este es tu saldo de referencia en el sistema."
    )


def cmd_set_actual(args: argparse.Namespace) -> Dict[str, Any]:
    state_path = resolve_data_path(args.state)
    state = load_saldo_state(state_path)

    amount: Optional[int] = None
    if args.amount is not None:
        amount = int(parse_clp(str(args.amount)) or 0)
    elif args.text:
        amount = parse_balance_text(args.text)
    if amount is None or amount < 0:
        return {
            "status": "error",
            "message": "No pude leer el monto. Usa --amount 1234567 o --text \"tengo 1.234.567\".",
        }

    now = datetime.now()
    as_of_date = (getattr(args, "as_of_date", None) or "").strip()[:10]
    if not as_of_date:
        as_of_date = now.strftime("%Y-%m-%d")
    entry = {
        "balance_clp": amount,
        "as_of_date": as_of_date,
        "as_of_datetime": now.isoformat(timespec="seconds"),
        "source": args.source or "user_manual",
        "notes": (args.note or "").strip(),
    }
    state["last_actual"] = entry
    anchors = list(state.get("anchors") or [])
    anchors.append(entry)
    state["anchors"] = anchors[-20:]
    save_saldo_state(state_path, state)

    summary = format_set_actual_reply(amount, entry)
    return {
        "status": "ok",
        "saved_actual_clp": amount,
        "anchor": entry,
        "expected_balance_clp": amount,
        "difference_clp": 0,
        "difference_ok": True,
        "summary": summary,
        "whatsapp_reply": summary,
    }


def cmd_report(args: argparse.Namespace) -> Dict[str, Any]:
    state_path = resolve_data_path(args.state)
    state = load_saldo_state(state_path)
    report = compute_expected(
        unified_csv=resolve_data_path(args.csv),
        cartola_csv=resolve_data_path(args.cartola),
        state=state,
    )
    actual: Optional[int] = None
    if args.actual is not None:
        actual = int(parse_clp(str(args.actual)) or 0)
    elif args.text:
        actual = parse_balance_text(args.text)
    elif isinstance(state.get("last_actual"), dict):
        actual = int(state["last_actual"].get("balance_clp") or 0) or None

    short = getattr(args, "short", False)
    summary = format_summary(report, actual=actual)
    whatsapp_reply = format_short_report(report) if short else summary
    payload: Dict[str, Any] = {
        "status": "ok",
        **report,
        "summary": summary,
        "whatsapp_reply": whatsapp_reply,
    }
    if actual is not None:
        expected = int(report.get("expected_balance_clp") or 0)
        payload["actual_balance_clp"] = actual
        payload["difference_clp"] = actual - expected
        payload["difference_ok"] = abs(payload["difference_clp"]) <= DIFF_TOLERANCE_CLP
        payload["causes"] = explain_difference(expected, actual, report)
    return payload


def cmd_bootstrap_cartola(args: argparse.Namespace) -> Dict[str, Any]:
    cartola_csv = resolve_data_path(args.cartola)
    anchor = last_cartola_balance(cartola_csv)
    if not anchor:
        return {"status": "error", "message": "No hay saldo en cartola CSV."}
    state_path = resolve_data_path(args.state)
    state = load_saldo_state(state_path)
    state["last_actual"] = anchor
    anchors = list(state.get("anchors") or [])
    anchors.append(anchor)
    state["anchors"] = anchors[-20:]
    save_saldo_state(state_path, state)
    report = compute_expected(
        unified_csv=resolve_data_path(args.csv),
        cartola_csv=cartola_csv,
        state=state,
    )
    summary = format_summary(report)
    return {
        "status": "ok",
        "anchor": anchor,
        "summary": summary,
        "whatsapp_reply": summary,
        **report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Saldo esperado vs real — Cuenta Corriente Santander.")
    parser.add_argument("--csv", default=DEFAULT_UNIFIED_CSV)
    parser.add_argument("--cartola", default=DEFAULT_CARTOLA_CSV)
    parser.add_argument("--state", default=DEFAULT_SALDO_STATE)

    sub = parser.add_subparsers(dest="command", required=True)

    p_report = sub.add_parser("report", help="Calcula saldo esperado; opcional compara con real.")
    p_report.add_argument("--actual", type=int, help="Saldo real CLP.")
    p_report.add_argument("--text", help="Texto con saldo (ej. tengo 1.234.567).")
    p_report.add_argument("--short", action="store_true", help="Respuesta corta para menu WhatsApp/Telegram.")
    p_report.add_argument("--json", action="store_true")

    p_set = sub.add_parser("set-actual", help="Guarda saldo real reportado por el usuario.")
    p_set.add_argument("--amount", type=int)
    p_set.add_argument("--text", help="Mensaje con el saldo.")
    p_set.add_argument("--source", default="user_manual")
    p_set.add_argument("--as-of-date", dest="as_of_date", help="YYYY-MM-DD fecha visible en app.")
    p_set.add_argument("--note", default="")
    p_set.add_argument("--json", action="store_true")

    p_boot = sub.add_parser("bootstrap-cartola", help="Ancla desde ultimo saldo cartola PDF.")
    p_boot.add_argument("--json", action="store_true")

    args = parser.parse_args()
    use_json = bool(getattr(args, "json", False))

    if args.command == "report":
        result = cmd_report(args)
    elif args.command == "set-actual":
        result = cmd_set_actual(args)
    elif args.command == "bootstrap-cartola":
        result = cmd_bootstrap_cartola(args)
    else:
        result = {"status": "error", "message": f"Comando desconocido: {args.command}"}

    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("summary") or result.get("message") or json.dumps(result, ensure_ascii=False))

    if result.get("status") == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
