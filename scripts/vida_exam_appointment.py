"""Procesa foto de orden médica: OCR visión + crea cita en Google Calendar."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vida_calendar_common import calendar_auth_hint
from vida_calendar_create import build_description, create_event, format_exams_list
from vida_common import ROOT, care_data, now_local, reply, save_json
from vida_exam_vision import DEFAULT_VISION_MODEL, apply_text_hints, call_vision

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
INBOUND_CANDIDATES = [
    ROOT / "data/config/media/inbound",
    Path("/home/node/.openclaw/media/inbound"),
    Path("/home/mauro/openclaw-mauro/data/config/media/inbound"),
]


def resolve_image(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    import time

    now = time.time()
    for inbound in INBOUND_CANDIDATES:
        if not inbound.exists():
            continue
        candidates = [
            p
            for p in inbound.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXT and (now - p.stat().st_mtime) <= 3600
        ]
        if candidates:
            return max(candidates, key=lambda p: p.stat().st_mtime)
    return None


def append_diary(note: str) -> None:
    day = now_local().strftime("%Y-%m-%d")
    path = care_data() / "diary" / f"{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = now_local().strftime("%H:%M")
    line = f"- [{stamp}] {note}\n"
    if path.exists():
        path.write_text(path.read_text(encoding="utf-8").rstrip() + "\n" + line, encoding="utf-8")
    else:
        path.write_text(f"# Diario {day}\n\n{line}", encoding="utf-8")


def save_appointment_record(record: dict) -> None:
    reg_path = care_data() / "appointments.json"
    reg = {"items": []}
    if reg_path.exists():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    reg.setdefault("items", []).append(record)
    save_json(reg_path, reg)


def build_title(parsed: dict) -> str:
    est = parsed.get("establishment") or "Exámenes médicos"
    if parsed.get("document_type") == "orden_laboratorio":
        return f"Exámenes laboratorio — {est}"
    return f"Cita médica — {est}"


def format_whatsapp_reply(parsed: dict, *, created: bool, event_link: str = "", error: str = "") -> str:
    date = parsed.get("appointment_date") or "?"
    time = parsed.get("appointment_time") or "?"
    est = parsed.get("establishment") or "centro de salud"
    exams = format_exams_list(parsed.get("exams") or [])

    lines = []
    if created:
        lines.append("*Cita agendada en Google Calendar* ✅")
    elif error:
        lines.append("*Orden leída, pero no pude crear la cita* ⚠️")
        lines.append(error)
    else:
        lines.append("*Orden médica procesada* (sin crear evento)")

    lines.append(f"• Fecha: {date}")
    lines.append(f"• Hora: {time}")
    lines.append(f"• Lugar: {est}")
    if parsed.get("establishment_address"):
        lines.append(f"• Dirección: {parsed['establishment_address']}")
    lines.append("")
    lines.append("*Exámenes:*")
    lines.append(exams)
    if event_link:
        lines.append("")
        lines.append(event_link)
    return "\n".join(lines)


def process_image(image_path: Path, text: str = "", *, dry_run: bool = False) -> dict:
    parsed = call_vision(image_path, DEFAULT_VISION_MODEL)
    parsed = apply_text_hints(parsed, text)

    if not parsed.get("exams") and parsed.get("document_type") == "otro":
        return reply(
            "La imagen no parece una orden de exámenes. Envía la orden médica o escribe "
            "`/care cita <fecha> <hora> <detalle>`.",
            status="error",
            parsed=parsed,
        )

    if not parsed.get("appointment_date") or not parsed.get("appointment_time"):
        exams_preview = format_exams_list(parsed.get("exams") or [])
        return reply(
            "Leí la orden pero falta *fecha u hora de la cita*.\n\n"
            f"*Exámenes detectados:*\n{exams_preview}\n\n"
            "Reenvía la foto con la fecha/hora manuscrita visible, o escribe:\n"
            "`/care cita 10/06/26 07:20` junto con la foto.",
            status="needs_datetime",
            parsed=parsed,
        )

    title = build_title(parsed)
    location = parsed.get("establishment_address") or parsed.get("establishment") or ""
    description = build_description(parsed, format_exams_list(parsed.get("exams") or []))

    if dry_run:
        msg = format_whatsapp_reply(parsed, created=False)
        return reply(msg, status="dry_run", parsed=parsed)

    try:
        event = create_event(
            title=title,
            date=parsed["appointment_date"],
            time=parsed["appointment_time"],
            location=location,
            description=description,
        )
        link = event.get("htmlLink", "")
        diary_note = (
            f"Cita exámenes {parsed['appointment_date']} {parsed['appointment_time']} — "
            f"{parsed.get('establishment') or 'médico'}"
        )
        append_diary(diary_note)
        save_appointment_record(
            {
                "created_at": now_local().isoformat(),
                "appointment_date": parsed["appointment_date"],
                "appointment_time": parsed["appointment_time"],
                "establishment": parsed.get("establishment"),
                "event_id": event.get("id"),
                "html_link": link,
                "exams": parsed.get("exams") or [],
                "image": str(image_path),
            }
        )
        msg = format_whatsapp_reply(parsed, created=True, event_link=link)
        return reply(msg, status="ok", parsed=parsed, event_id=event.get("id"), html_link=link)
    except Exception as exc:
        err = str(exc)
        if "no autorizado" in err.lower() or "calendar" in err.lower():
            err = calendar_auth_hint()
        msg = format_whatsapp_reply(parsed, created=False, error=err)
        return reply(msg, status="error", parsed=parsed)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=None)
    ap.add_argument("--text", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    image_path = resolve_image(args.image)
    if not image_path:
        out = reply(
            "No encontré foto reciente. Envía la imagen de la orden y escribe `/care` o "
            "`/care agenda examen`.",
            status="error",
        )
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])
        return

    out = process_image(image_path, args.text, dry_run=args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out["whatsapp_reply"])


if __name__ == "__main__":
    main()
