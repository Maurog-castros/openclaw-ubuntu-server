"""Esquema CSV unificado y utilidades compartidas para agentes de finanzas."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

UNIFIED_COLUMNS = [
    "processed_at",
    "movement_id",
    "movement_type",
    "source",
    "movement_date",
    "movement_time",
    "movement_datetime",
    "merchant",
    "merchant_rut",
    "merchant_branch",
    "document_number",
    "reference_id",
    "description",
    "category",
    "amount_clp",
    "ticket_total",
    "payment_method",
    "counterparty",
    "counterparty_rut",
    "raw_source_file",
]

VISION_CSV_COLUMNS = [
    "processed_at",
    "source",
    "source_ref",
    "image_path",
    "image_hash",
    "purchase_date",
    "purchase_time",
    "purchase_datetime",
    "store",
    "store_branch",
    "merchant_rut",
    "receipt_number",
    "product",
    "category",
    "line_amount",
    "ticket_total",
    "payment_method",
    "model_used",
]

DEFAULT_UNIFIED_CSV = "data/finanzas_movimientos.csv"
DEFAULT_VISION_CSV = "data/receipts_vision.csv"
DEFAULT_LIDER_CSV = "data/lider_receipts.csv"
DEFAULT_TRANSFERENCIAS_CSV = "data/transferencias.csv"
DEFAULT_CARTOLA_CSV = "data/santander_cartola.csv"
DEFAULT_RECEIPTS_REGISTRY = "data/receipts_registry.json"
DEFAULT_MERCHANT_ALIASES = "data/finanzas_merchant_aliases.json"
DEFAULT_OBSERVACIONES = "data/finanzas_observaciones.json"
DEFAULT_SALDO_STATE = "data/finanzas_saldo_state.json"
DEFAULT_MOVIMIENTO_LINKS = "data/finanzas_movimiento_links.json"

TRANSFER_SOURCE_PRIORITY = {
    "santander_gmail": 100,
    "santander_cartola": 95,
    "santander_app": 80,
    "transferencias_gmail": 90,
    "telegram_foto": 20,
    "whatsapp_foto": 10,
    "openclaw_web": 15,
    "manual": 5,
}

TRANSFER_SOURCE_LABELS = {
    "santander_gmail": "Gmail comprobante",
    "santander_cartola": "cartola banco",
    "santander_app": "screenshot app Santander",
    "whatsapp_foto": "OCR screenshot app (misma tx, no boleta)",
    "telegram_foto": "foto Telegram",
    "manual": "manual",
}

_REPO_ROOT = Path(__file__).resolve().parent.parent


def repo_root() -> Path:
    return _REPO_ROOT


def resolve_data_path(path: str | Path) -> Path:
    """Rutas data/... relativas al repo, no al cwd del agente."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return repo_root() / candidate


def load_merchant_aliases(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    aliases = data.get("aliases") if isinstance(data, dict) else data
    if not isinstance(aliases, list):
        return []
    return [entry for entry in aliases if isinstance(entry, dict)]


def save_merchant_aliases(path: Path, aliases: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"aliases": aliases}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_observaciones(path: Path) -> Dict[str, Dict[str, str]]:
    """movement_id -> {note, updated_at, movement_date, amount_clp, label}."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    notes = data.get("notes") if isinstance(data, dict) else data
    if not isinstance(notes, dict):
        return {}
    return {str(k): v for k, v in notes.items() if isinstance(v, dict)}


def save_observaciones(path: Path, notes: Dict[str, Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"notes": notes}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_movimiento_links(path: Path) -> Dict[str, Dict[str, Any]]:
    """movement_id secundario -> {canonical_movement_id, exclude_from_totals, note, ...}."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    links = data.get("links") if isinstance(data, dict) else data
    if not isinstance(links, dict):
        return {}
    return {str(k): v for k, v in links.items() if isinstance(v, dict)}


def save_movimiento_links(path: Path, links: Dict[str, Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"links": links}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def is_excluded_from_totals(movement_id: str, links: Dict[str, Dict[str, Any]]) -> bool:
    entry = links.get(movement_id or "")
    return bool(entry and entry.get("exclude_from_totals"))


def transfer_source_priority(source: str) -> int:
    return int(TRANSFER_SOURCE_PRIORITY.get(source or "", 0))


def movement_row_text(row: Dict[str, str]) -> str:
    return " ".join(
        [
            row.get("description") or "",
            row.get("counterparty") or "",
            row.get("merchant") or "",
            row.get("document_number") or "",
        ]
    )


def pick_canonical_transfer(rows: List[Dict[str, str]]) -> Dict[str, str]:
    """Elige registro canonico: transferencia_salida > gasto; mayor prioridad de fuente."""
    if not rows:
        raise ValueError("empty group")

    def score(row: Dict[str, str]) -> tuple[int, int, str]:
        mt = (row.get("movement_type") or "").lower()
        type_score = 10 if mt.startswith("transferencia") else 0
        src_score = transfer_source_priority(row.get("source") or "")
        date = row.get("movement_date") or ""
        return (type_score, src_score, date)

    return max(rows, key=score)


def link_label(row: Dict[str, str]) -> str:
    src = row.get("source") or "?"
    label = TRANSFER_SOURCE_LABELS.get(src, src)
    desc = movement_label(row)[:60]
    return f"{label}: {desc}"


def parse_flexible_date(value: str) -> str:
    """Devuelve YYYY-MM-DD o vacio."""
    text = (value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    match = re.fullmatch(r"(\d{2})-(\d{2})-(\d{2,4})", text)
    if match:
        d, m, y = match.groups()
        if len(y) == 2:
            y = f"20{y}"
        return f"{y}-{m}-{d}"
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", text)
    if match:
        d, m, y = match.groups()
        return f"{y}-{m}-{d}"
    return ""


def movement_label(row: Dict[str, str]) -> str:
    return (row.get("description") or row.get("counterparty") or row.get("merchant") or "").strip()


def find_movements(
    rows: Iterable[Dict[str, str]],
    *,
    movement_id: str = "",
    movement_date: str = "",
    amount_clp: Optional[int] = None,
    counterparty_contains: str = "",
    movement_type: str = "",
    description_contains: str = "",
) -> List[Dict[str, str]]:
    target_id = (movement_id or "").strip()
    target_date = parse_flexible_date(movement_date)
    needle_counterparty = normalize_store_name(counterparty_contains)
    needle_description = normalize_store_name(description_contains)
    target_type = (movement_type or "").strip().lower()

    matches: List[Dict[str, str]] = []
    for row in rows:
        if target_id and (row.get("movement_id") or "") != target_id:
            continue
        if target_date and (row.get("movement_date") or "")[:10] != target_date:
            continue
        if target_type and (row.get("movement_type") or "").lower() != target_type:
            continue
        if amount_clp is not None:
            row_amount = parse_clp(row.get("amount_clp") or row.get("ticket_total"))
            if row_amount is None or int(row_amount) != int(amount_clp):
                continue
        if needle_counterparty:
            hay = normalize_store_name(
                " ".join(
                    [
                        row.get("counterparty") or "",
                        row.get("description") or "",
                        row.get("merchant") or "",
                    ]
                )
            )
            if needle_counterparty not in hay:
                continue
        if needle_description:
            if needle_description not in normalize_store_name(row.get("description") or ""):
                continue
        if not target_id and not target_date and amount_clp is None and not needle_counterparty:
            continue
        matches.append(row)
    return matches


def row_search_text(row: Dict[str, str]) -> str:
    parts = [
        row.get("merchant") or "",
        row.get("description") or "",
        row.get("merchant_branch") or "",
        row.get("counterparty") or "",
        row.get("category") or "",
    ]
    return normalize_store_name(" ".join(parts))


def alias_patterns(alias: Dict[str, Any]) -> List[str]:
    patterns: List[str] = []
    for key in ("label", "id"):
        value = str(alias.get(key) or "").strip()
        if value:
            patterns.append(normalize_store_name(value))
    for item in alias.get("patterns") or []:
        text = normalize_store_name(str(item))
        if text:
            patterns.append(text)
    return patterns


def row_matches_alias(row: Dict[str, str], alias: Dict[str, Any]) -> bool:
    haystack = row_search_text(row)
    if not haystack:
        return False
    for pattern in alias_patterns(alias):
        if pattern and pattern in haystack:
            return True
    return False


def find_alias_by_query(aliases: List[Dict[str, Any]], query: str) -> Optional[Dict[str, Any]]:
    needle = normalize_store_name(query)
    if not needle:
        return None
    exact: List[Dict[str, Any]] = []
    partial: List[Dict[str, Any]] = []
    for alias in aliases:
        alias_id = normalize_store_name(str(alias.get("id") or ""))
        alias_label = normalize_store_name(str(alias.get("label") or ""))
        if needle == alias_id or needle == alias_label:
            exact.append(alias)
            continue
        if needle in alias_id or needle in alias_label:
            partial.append(alias)
            continue
        if any(needle in pattern for pattern in alias_patterns(alias)):
            partial.append(alias)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return exact[0]
    if len(partial) == 1:
        return partial[0]
    return None


SOURCE_PRIORITY = {
    "lider_gmail": 100,
    "santander_cartola": 95,
    "santander_gmail": 90,
    "santander_app": 80,
    "telegram_foto": 50,
    "whatsapp_foto": 50,
    "openclaw_web": 40,
    "manual": 30,
}


def category_for_product(name: str) -> str:
    lowered = (name or "").lower()
    rules = {
        "salud_farmacia": [
            "farmacia",
            "simi",
            "medic",
            "vitamin",
            "pomada",
            "capsula",
            "comprim",
            "aspir",
            "paracet",
            "ibuprof",
        ],
        "frutas_verduras": ["manzana", "platano", "palta", "lechuga", "tomate", "cebolla"],
        "carnes_pescados": ["pollo", "vacuno", "cerdo", "salmon", "atun", "filet", "churrasco"],
        "lacteos_huevos": ["leche", "queso", "yogurt", "huevo", "mantequilla"],
        "panaderia": ["pan", "hallulla", "marraqueta", "molde", "tortilla"],
        "limpieza_hogar": ["detergente", "lavaloza", "cloro", "suavizante", "papel higienico"],
        "cuidado_personal": ["shampoo", "jabon", "desodorante", "pasta dental"],
        "bebidas": ["coca", "jugo", "agua", "cerveza", "vino", "bebida", "refresco"],
        "embutidos": ["jamon", "jamón", "salchicha", "mortadela"],
        "despensa": ["arroz", "fideo", "aceite", "azucar", "sal", "harina", "sardina"],
    }
    for category, keywords in rules.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "otros"


def ensure_csv_headers(csv_file: Path, columns: List[str]) -> None:
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    if not csv_file.exists():
        with csv_file.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(columns)
        return

    with csv_file.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        existing = reader.fieldnames or []
        if all(col in existing for col in columns):
            return
        rows = list(reader)

    merged = list(existing)
    for col in columns:
        if col not in merged:
            merged.append(col)

    with csv_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=merged)
        writer.writeheader()
        for row in rows:
            for col in merged:
                row.setdefault(col, "")
            writer.writerow(row)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_movement_id(*parts: Any) -> str:
    raw = "|".join(str(part or "").strip().lower() for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def normalize_rut(value: str) -> str:
    return re.sub(r"[^0-9kK]", "", (value or "")).lower()


def normalize_store_name(value: str) -> str:
    text = (value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    for token in ("limitada", "ltda", "spa", "s a", "sa", "chile"):
        text = text.replace(token, " ")
    return re.sub(r"\s+", " ", text).strip()


def make_receipt_fingerprint(
    *,
    receipt_number: str = "",
    merchant_rut: str = "",
    store: str = "",
    purchase_date: str = "",
    ticket_total: Any = None,
) -> Optional[str]:
    total = parse_clp(ticket_total)
    date = str(purchase_date or "").strip()
    doc = re.sub(r"\D", "", str(receipt_number or ""))
    merchant = normalize_store_name(store)

    if total is None or total <= 0:
        return None

    # Fuerte: nº documento + fecha + total (tolera OCR distinto en comercio/RUT)
    if doc and len(doc) >= 4 and date:
        return make_movement_id("receipt", "doc", doc, date, total)

    if date and merchant and len(merchant) >= 3:
        return make_movement_id("receipt", "fuzzy", merchant, date, total)

    return None


def fingerprint_from_receipt_dict(receipt: Dict[str, Any]) -> Optional[str]:
    return make_receipt_fingerprint(
        receipt_number=str(receipt.get("receipt_number") or ""),
        merchant_rut=str(receipt.get("merchant_rut") or ""),
        store=str(receipt.get("store") or ""),
        purchase_date=str(receipt.get("purchase_date") or ""),
        ticket_total=receipt.get("ticket_total"),
    )


def fingerprint_from_vision_row(row: Dict[str, str]) -> Optional[str]:
    return make_receipt_fingerprint(
        receipt_number=row.get("receipt_number") or "",
        merchant_rut=row.get("merchant_rut") or "",
        store=row.get("store") or "",
        purchase_date=row.get("purchase_date") or "",
        ticket_total=row.get("ticket_total") or row.get("line_amount"),
    )


def fingerprint_from_lider_row(row: Dict[str, str]) -> Optional[str]:
    return make_receipt_fingerprint(
        receipt_number=row.get("receipt_number") or "",
        merchant_rut="",
        store=row.get("store") or "lider",
        purchase_date=row.get("purchase_date") or "",
        ticket_total=row.get("ticket_total") or row.get("line_amount"),
    )


def fingerprint_from_unified_row(row: Dict[str, str]) -> Optional[str]:
    if row.get("movement_type") != "gasto":
        return None
    return make_receipt_fingerprint(
        receipt_number=row.get("document_number") or "",
        merchant_rut=row.get("merchant_rut") or "",
        store=row.get("merchant") or "",
        purchase_date=row.get("movement_date") or "",
        ticket_total=row.get("ticket_total") or row.get("amount_clp"),
    )


def load_receipt_registry(registry_file: Path, legacy_state_file: Optional[Path] = None) -> Dict[str, Any]:
    registry: Dict[str, Any] = {"fingerprints": {}, "image_hashes": {}}
    if registry_file.exists():
        try:
            loaded = json.loads(registry_file.read_text(encoding="utf-8"))
            if isinstance(loaded.get("fingerprints"), dict):
                registry["fingerprints"] = loaded["fingerprints"]
            if isinstance(loaded.get("image_hashes"), dict):
                registry["image_hashes"] = loaded["image_hashes"]
            elif isinstance(loaded.get("image_hashes"), list):
                registry["image_hashes"] = {item: True for item in loaded["image_hashes"]}
        except json.JSONDecodeError:
            pass

    if legacy_state_file and legacy_state_file.exists():
        try:
            legacy = json.loads(legacy_state_file.read_text(encoding="utf-8"))
            for key, value in legacy.items():
                if value is True or value == "true":
                    registry["image_hashes"].setdefault(key, True)
        except json.JSONDecodeError:
            pass

    return registry


def save_receipt_registry(registry_file: Path, registry: Dict[str, Any]) -> None:
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    registry_file.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")


def is_image_processed(registry: Dict[str, Any], image_hash: str) -> bool:
    return bool(registry.get("image_hashes", {}).get(image_hash))


def find_receipt_duplicate(registry: Dict[str, Any], fingerprint: Optional[str]) -> Optional[Dict[str, Any]]:
    if not fingerprint:
        return None
    entry = registry.get("fingerprints", {}).get(fingerprint)
    if isinstance(entry, dict):
        return entry
    return None


def register_image_hash(registry: Dict[str, Any], image_hash: str) -> None:
    registry.setdefault("image_hashes", {})[image_hash] = True


def register_receipt_fingerprint(
    registry: Dict[str, Any],
    fingerprint: str,
    *,
    store: str,
    receipt_number: str,
    merchant_rut: str,
    purchase_date: str,
    ticket_total: Any,
    source: str,
    image_hash: str = "",
    processed_at: str = "",
) -> None:
    registry.setdefault("fingerprints", {})[fingerprint] = {
        "store": store,
        "receipt_number": receipt_number,
        "merchant_rut": merchant_rut,
        "purchase_date": purchase_date,
        "ticket_total": parse_clp(ticket_total),
        "source": source,
        "image_hash": image_hash,
        "processed_at": processed_at or datetime.now().isoformat(timespec="seconds"),
    }


def seed_registry_from_csvs(
    registry: Dict[str, Any],
    *,
    vision_csv: Path,
    lider_csv: Path,
    unified_csv: Optional[Path] = None,
) -> None:
    seen_tickets: Dict[str, Dict[str, str]] = {}

    for row in read_csv_rows(lider_csv):
        fp = fingerprint_from_lider_row(row)
        if not fp or fp in seen_tickets:
            continue
        seen_tickets[fp] = {
            "store": row.get("store") or "lider",
            "receipt_number": row.get("receipt_number") or "",
            "merchant_rut": "",
            "purchase_date": row.get("purchase_date") or "",
            "ticket_total": row.get("ticket_total") or "",
            "source": "lider_gmail",
            "image_hash": "",
            "processed_at": row.get("processed_at") or "",
        }

    for row in read_csv_rows(vision_csv):
        fp = fingerprint_from_vision_row(row)
        if not fp or fp in seen_tickets:
            continue
        seen_tickets[fp] = {
            "store": row.get("store") or "",
            "receipt_number": row.get("receipt_number") or "",
            "merchant_rut": row.get("merchant_rut") or "",
            "purchase_date": row.get("purchase_date") or "",
            "ticket_total": row.get("ticket_total") or "",
            "source": row.get("source") or "telegram_foto",
            "image_hash": row.get("image_hash") or "",
            "processed_at": row.get("processed_at") or "",
        }

    if unified_csv:
        for row in read_csv_rows(unified_csv):
            fp = fingerprint_from_unified_row(row)
            if not fp or fp in seen_tickets:
                continue
            seen_tickets[fp] = {
                "store": row.get("merchant") or "",
                "receipt_number": row.get("document_number") or "",
                "merchant_rut": row.get("merchant_rut") or "",
                "purchase_date": row.get("movement_date") or "",
                "ticket_total": row.get("ticket_total") or "",
                "source": row.get("source") or "",
                "image_hash": "",
                "processed_at": row.get("processed_at") or "",
            }

    for fp, meta in seen_tickets.items():
        if fp not in registry.get("fingerprints", {}):
            register_receipt_fingerprint(registry, fp, **meta)


def parse_clp(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(round(value))
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("$", "").strip()
    # Floats serializados en CSV (11496.0, 2850.0) — no son miles chilenos.
    if re.fullmatch(r"\d+\.0+", text):
        try:
            return int(round(float(text)))
        except ValueError:
            return None
    # Miles chilenos: 11.496, 114.960, 1.234.567
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
        return int(text.replace(".", ""))
    if re.fullmatch(r"\d+\.\d{3}", text):
        left, right = text.split(".", 1)
        return int(left + right)
    cleaned = text.replace(".", "").replace(",", ".")
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def read_csv_rows(csv_file: Path) -> List[Dict[str, str]]:
    if not csv_file.exists():
        return []
    with csv_file.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def rows_from_vision_record(record: Dict[str, Any], metadata: Dict[str, str]) -> List[Dict[str, str]]:
    processed_at = metadata.get("processed_at") or datetime.now().isoformat(timespec="seconds")
    source = metadata.get("source") or record.get("source") or "telegram_foto"
    source_ref = metadata.get("source_ref") or record.get("source_ref") or ""
    image_path = metadata.get("image_path") or ""
    model_used = metadata.get("model_used") or ""

    purchase_date = record.get("purchase_date") or ""
    purchase_time = record.get("purchase_time") or ""
    purchase_datetime = record.get("purchase_datetime") or ""
    if not purchase_datetime and purchase_date:
        purchase_datetime = f"{purchase_date} {purchase_time}".strip()

    store = record.get("store") or ""
    store_branch = record.get("store_branch") or ""
    merchant_rut = record.get("merchant_rut") or ""
    receipt_number = str(record.get("receipt_number") or "")
    payment_method = record.get("payment_method") or ""
    ticket_total = parse_clp(record.get("ticket_total"))

    items = record.get("items") or []
    if not items:
        items = [{"product": "boleta_sin_detalle_detectado", "amount": ticket_total, "category": "otros"}]

    rows: List[Dict[str, str]] = []
    for item in items:
        product = item.get("product") or item.get("name") or "item_sin_nombre"
        category = item.get("category") or category_for_product(product)
        amount = parse_clp(item.get("amount") or item.get("line_amount"))
        fingerprint = fingerprint_from_receipt_dict(record)
        movement_id = make_movement_id(
            "gasto",
            fingerprint or "no_fp",
            product,
            amount,
            purchase_date,
        )
        rows.append(
            {
                "processed_at": processed_at,
                "movement_id": movement_id,
                "movement_type": "gasto",
                "source": source,
                "movement_date": purchase_date,
                "movement_time": purchase_time,
                "movement_datetime": purchase_datetime,
                "merchant": store,
                "merchant_rut": merchant_rut,
                "merchant_branch": store_branch,
                "document_number": receipt_number,
                "reference_id": source_ref or receipt_number,
                "description": product,
                "category": category,
                "amount_clp": str(amount or ""),
                "ticket_total": str(ticket_total or ""),
                "payment_method": payment_method,
                "counterparty": "",
                "counterparty_rut": "",
                "raw_source_file": image_path,
            }
        )
    return rows


def rows_from_lider_csv(lider_csv: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for row in read_csv_rows(lider_csv):
        product = row.get("product") or ""
        amount = parse_clp(row.get("line_amount"))
        ticket_total = parse_clp(row.get("ticket_total"))
        fingerprint = fingerprint_from_lider_row(row)
        movement_id = make_movement_id(
            "gasto",
            fingerprint or "no_fp",
            product,
            amount,
            row.get("purchase_date"),
        )
        rows.append(
            {
                "processed_at": row.get("processed_at") or "",
                "movement_id": movement_id,
                "movement_type": "gasto",
                "source": "lider_gmail",
                "movement_date": row.get("purchase_date") or "",
                "movement_time": row.get("purchase_time") or "",
                "movement_datetime": row.get("purchase_datetime") or "",
                "merchant": row.get("store") or "lider",
                "merchant_rut": "",
                "merchant_branch": row.get("store_branch") or "",
                "document_number": row.get("receipt_number") or "",
                "reference_id": row.get("message_id") or "",
                "description": product,
                "category": row.get("category") or category_for_product(product),
                "amount_clp": str(amount or ""),
                "ticket_total": str(ticket_total or ""),
                "payment_method": "",
                "counterparty": "",
                "counterparty_rut": "",
                "raw_source_file": row.get("attachment_name") or "",
            }
        )
    return rows


def rows_from_vision_csv(vision_csv: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for row in read_csv_rows(vision_csv):
        product = row.get("product") or ""
        amount = parse_clp(row.get("line_amount"))
        ticket_total = parse_clp(row.get("ticket_total"))
        fingerprint = fingerprint_from_vision_row(row)
        movement_id = make_movement_id(
            "gasto",
            fingerprint or "no_fp",
            product,
            amount,
            row.get("purchase_date"),
        )
        rows.append(
            {
                "processed_at": row.get("processed_at") or "",
                "movement_id": movement_id,
                "movement_type": "gasto",
                "source": row.get("source") or "telegram_foto",
                "movement_date": row.get("purchase_date") or "",
                "movement_time": row.get("purchase_time") or "",
                "movement_datetime": row.get("purchase_datetime") or "",
                "merchant": row.get("store") or "",
                "merchant_rut": row.get("merchant_rut") or "",
                "merchant_branch": row.get("store_branch") or "",
                "document_number": row.get("receipt_number") or "",
                "reference_id": row.get("source_ref") or row.get("image_hash") or "",
                "description": product,
                "category": row.get("category") or category_for_product(product),
                "amount_clp": str(amount or ""),
                "ticket_total": str(ticket_total or ""),
                "payment_method": row.get("payment_method") or "",
                "counterparty": "",
                "counterparty_rut": "",
                "raw_source_file": row.get("image_path") or "",
            }
        )
    return rows


def rows_from_transferencias_csv(transferencias_csv: Path, owner_rut: str = "") -> List[Dict[str, str]]:
    """Comprobantes Gmail Santander: siempre salida desde la cuenta principal (origen en el mail)."""
    rows: List[Dict[str, str]] = []
    owner_rut_norm = re.sub(r"[^0-9kK]", "", owner_rut or "").lower()
    for row in read_csv_rows(transferencias_csv):
        amount = parse_clp(row.get("amount_clp"))
        if amount is None:
            continue

        destination_rut = row.get("destination_rut") or ""
        destination_norm = re.sub(r"[^0-9kK]", "", destination_rut).lower()
        movement_type = "transferencia_salida"
        counterparty = row.get("destination_name") or ""
        counterparty_rut = destination_rut

        description = (row.get("comment") or "").strip()
        if not description:
            bank = row.get("destination_bank") or ""
            if owner_rut_norm and destination_norm == owner_rut_norm:
                description = "Transferencia a cuenta propia"
            else:
                description = f"Transferencia a {counterparty}"
            if bank:
                description += f" ({bank})"
        movement_id = make_movement_id(
            "transferencia",
            row.get("message_id"),
            movement_type,
            amount,
            row.get("transfer_date"),
            counterparty_rut,
        )
        rows.append(
            {
                "processed_at": row.get("processed_at") or "",
                "movement_id": movement_id,
                "movement_type": movement_type,
                "source": "santander_gmail",
                "movement_date": row.get("transfer_date") or "",
                "movement_time": "",
                "movement_datetime": row.get("email_date") or row.get("transfer_date") or "",
                "merchant": "santander",
                "merchant_rut": "",
                "merchant_branch": "",
                "document_number": "",
                "reference_id": row.get("message_id") or "",
                "description": description,
                "category": "transferencias",
                "amount_clp": str(amount),
                "ticket_total": str(amount),
                "payment_method": "transferencia",
                "counterparty": counterparty,
                "counterparty_rut": counterparty_rut,
                "raw_source_file": row.get("raw_subject") or "",
            }
        )
    return rows


def _category_from_cartola_description(description: str) -> str:
    lowered = (description or "").lower()
    if "transf" in lowered:
        return "transferencias"
    if "lider" in lowered or "hiper" in lowered:
        return "supermercado"
    if "compra" in lowered:
        return "compras_tarjeta"
    if "giro" in lowered:
        return "efectivo"
    return "banco"


def rows_from_cartola_csv(cartola_csv: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for row in read_csv_rows(cartola_csv):
        charge = parse_clp(row.get("charge_clp")) or 0
        credit = parse_clp(row.get("credit_clp")) or 0
        amount = charge or credit
        if amount <= 0:
            continue
        description = row.get("description") or ""
        if charge:
            movement_type = "transferencia_salida" if "transf" in description.lower() else "gasto"
        else:
            movement_type = "transferencia_entrada" if "transf" in description.lower() else "ingreso"

        merchant = "santander"
        if "lider" in description.lower():
            merchant = "lider"
        elif "transf" in description.lower():
            merchant = "santander"

        movement_id = make_movement_id(
            "cartola",
            row.get("message_id"),
            row.get("document_number"),
            amount,
            row.get("movement_date"),
            description[:40],
        )
        rows.append(
            {
                "processed_at": row.get("processed_at") or "",
                "movement_id": movement_id,
                "movement_type": movement_type,
                "source": "santander_cartola",
                "movement_date": row.get("movement_date") or "",
                "movement_time": "",
                "movement_datetime": row.get("movement_date") or "",
                "merchant": merchant,
                "merchant_rut": "",
                "merchant_branch": row.get("branch") or "",
                "document_number": row.get("document_number") or "",
                "reference_id": row.get("message_id") or "",
                "description": description,
                "category": _category_from_cartola_description(description),
                "amount_clp": str(amount),
                "ticket_total": str(amount),
                "payment_method": "tarjeta" if charge and "compra" in description.lower() else "transferencia",
                "counterparty": "",
                "counterparty_rut": "",
                "raw_source_file": row.get("pdf_filename") or "",
            }
        )
    return rows


def dedupe_rows(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: set[str] = set()
    out: List[Dict[str, str]] = []
    for row in rows:
        movement_id = row.get("movement_id") or ""
        if not movement_id or movement_id in seen:
            continue
        seen.add(movement_id)
        out.append(row)
    return out


def dedupe_gastos_by_receipt(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Una boleta = una fuente. Prioridad: lider_gmail > telegram_foto > manual."""
    transfers: List[Dict[str, str]] = []
    gastos: List[Dict[str, str]] = []
    for row in rows:
        if row.get("movement_type", "").startswith("transferencia"):
            transfers.append(row)
        else:
            gastos.append(row)

    groups: Dict[str, List[Dict[str, str]]] = {}
    no_fp: List[Dict[str, str]] = []
    for row in gastos:
        fp = fingerprint_from_unified_row(row)
        if not fp:
            no_fp.append(row)
            continue
        groups.setdefault(fp, []).append(row)

    kept_gastos: List[Dict[str, str]] = []
    for fp, group in groups.items():
        sources = {row.get("source") or "" for row in group}
        if len(sources) == 1:
            kept_gastos.extend(group)
            continue
        best_source = max(sources, key=lambda src: SOURCE_PRIORITY.get(src, 0))
        kept_gastos.extend(row for row in group if (row.get("source") or "") == best_source)

    merged = dedupe_rows(transfers + kept_gastos + no_fp)
    return merged


def write_unified_csv(csv_file: Path, rows: List[Dict[str, str]]) -> None:
    ensure_csv_headers(csv_file, UNIFIED_COLUMNS)
    with csv_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=UNIFIED_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in UNIFIED_COLUMNS})


def merge_all_sources(
    unified_csv: Path,
    lider_csv: Path,
    vision_csv: Path,
    transferencias_csv: Path,
    owner_rut: str = "",
    registry_file: Optional[Path] = None,
    cartola_csv: Optional[Path] = None,
) -> Dict[str, int]:
    registry_path = registry_file or unified_csv.parent / "receipts_registry.json"
    registry = load_receipt_registry(registry_path)
    seed_registry_from_csvs(
        registry,
        vision_csv=vision_csv,
        lider_csv=lider_csv,
        unified_csv=unified_csv if unified_csv.exists() else None,
    )
    save_receipt_registry(registry_path, registry)

    cartola_path = cartola_csv or unified_csv.parent / "santander_cartola.csv"
    merged = dedupe_gastos_by_receipt(
        rows_from_lider_csv(lider_csv)
        + rows_from_vision_csv(vision_csv)
        + rows_from_transferencias_csv(transferencias_csv, owner_rut=owner_rut)
        + rows_from_cartola_csv(cartola_path)
    )
    merged.sort(
        key=lambda row: (row.get("movement_datetime") or row.get("movement_date") or "", row.get("movement_id")),
        reverse=True,
    )
    write_unified_csv(unified_csv, merged)
    return {
        "lider": len(rows_from_lider_csv(lider_csv)),
        "vision": len(rows_from_vision_csv(vision_csv)),
        "transferencias": len(rows_from_transferencias_csv(transferencias_csv, owner_rut=owner_rut)),
        "cartola": len(rows_from_cartola_csv(cartola_path)),
        "unified": len(merged),
    }


def extract_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No se encontro JSON valido en la respuesta del modelo.")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("La respuesta del modelo no es un objeto JSON.")
    return parsed
