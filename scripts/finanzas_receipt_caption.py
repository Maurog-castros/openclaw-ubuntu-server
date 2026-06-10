"""Caption de usuario (WhatsApp) y deteccion de screenshots bancarios."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from finanzas_common import category_for_product, parse_clp

FIN_PREFIX_RE = re.compile(r"^\s*/(?:fin|finanzas)\b\s*", re.I)
QUERY_RE = re.compile(
    r"\b(cuanto|como|cuales|cual|ultim|saldo|transfer|gast|report|menu|help|status)\b",
    re.I,
)
GENERIC_PRODUCTS = frozenset(
    {
        "compra afecta",
        "compra",
        "boleta_sin_detalle_detectado",
        "descripcion del producto no especificada",
        "item_sin_nombre",
        "item",
    }
)
BANK_LINE_RE = re.compile(r"\b(TRANSF\s|TRANSFERENCIA|078\d{7,})\b", re.I)
GENERIC_STORES = frozenset({"", "desconocido", "getnet"})


def strip_fin_prefix(text: str) -> str:
    return FIN_PREFIX_RE.sub("", text or "").strip()


def extract_caption_products(text: str) -> List[str]:
    t = strip_fin_prefix(text or "").strip()
    if not t or len(t) < 3:
        return []
    if QUERY_RE.search(t):
        return []
    if t.startswith("/"):
        return []
    parts = [p.strip() for p in re.split(r"\s*[+,]\s*", t) if p.strip()]
    return [p for p in parts if len(p) >= 2]


def is_generic_product(name: str) -> bool:
    n = (name or "").strip().lower()
    if not n:
        return True
    if n in GENERIC_PRODUCTS:
        return True
    return n.startswith("compra") and len(n) <= 24


def looks_like_equal_split(items: List[Dict[str, Any]], ticket_total: int) -> bool:
    """Detecta montos inventados repartiendo el total en partes iguales."""
    if len(items) < 2 or not ticket_total:
        return False
    amounts = [parse_clp(i.get("amount")) or 0 for i in items]
    if sum(amounts) != ticket_total:
        return False
    avg = ticket_total / len(amounts)
    return all(abs(amount - avg) <= max(10, ticket_total * 0.02) for amount in amounts)


def enrich_receipt_from_caption(receipt: Dict[str, Any], caption: str) -> Dict[str, Any]:
    products = extract_caption_products(caption)
    if not products:
        return receipt

    items: List[Dict[str, Any]] = list(receipt.get("items") or [])
    ticket_total = parse_clp(receipt.get("ticket_total")) or 0
    caption_text = strip_fin_prefix(caption).strip()
    generic_items = not items or all(is_generic_product(str(i.get("product") or "")) for i in items)
    split_artifact = looks_like_equal_split(items, ticket_total)

    # Caption describe productos; el total viene del OCR de la boleta. Nunca repartir a ojo.
    if generic_items or split_artifact or len(products) > 1:
        items = [
            {
                "product": caption_text,
                "quantity": 1,
                "amount": ticket_total or (parse_clp(items[0].get("amount")) if items else 0),
                "category": category_for_product(caption_text),
            }
        ]
    elif len(products) == 1 and len(items) == 1:
        items[0]["product"] = products[0]
        if ticket_total:
            items[0]["amount"] = ticket_total

    receipt = dict(receipt)
    receipt["items"] = items
    receipt["user_caption"] = caption_text
    validation = dict(receipt.get("validation") or {})
    line_sum = sum(parse_clp(i.get("amount")) or 0 for i in items)
    if ticket_total and line_sum == ticket_total:
        validation["ok"] = True
        validation["issues"] = []
    receipt["validation"] = validation
    return receipt


def looks_like_bank_screenshot(receipt: Dict[str, Any]) -> bool:
    items = receipt.get("items") or []
    if len(items) < 2:
        return False

    store = (receipt.get("store") or "").strip().lower()
    ticket_total = parse_clp(receipt.get("ticket_total")) or 0
    line_sum = sum(parse_clp(i.get("amount")) or 0 for i in items)

    if any(BANK_LINE_RE.search(str(i.get("product") or "")) for i in items):
        return True

    if store in GENERIC_STORES and len(items) >= 2:
        if ticket_total and line_sum != ticket_total:
            return True
        merchants = {str(i.get("product") or "").split()[0].upper() for i in items}
        if len(merchants) >= 2:
            return True

    if ticket_total and line_sum > ticket_total * 2:
        return True

    return False


def display_merchant_name(merchant: str, branch: str) -> str:
    m = (merchant or "").strip()
    b = (branch or "").strip()
    if m.upper() in ("GETNET", "DESCONOCIDO") and b:
        return b.split(" Calle")[0].split(" Av.")[0].split(",")[0].strip() or m
    if m.upper() == "MERCADO PAGO" and b:
        return b.split(",")[0].strip() or m
    return m or b or "desconocido"
