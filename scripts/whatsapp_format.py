"""Formato nativo WhatsApp (*negrita*, emojis, sin tablas markdown)."""

from __future__ import annotations

import re
from typing import List

TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}")
HEADER_LINE_RE = re.compile(r"^={3,}\s*(.+?)\s*={3,}\s*$")
SECTION_RE = re.compile(r"^(Por tipo|Por categoria|Por categoría|Top comercios|Fuentes|Detalle|Movimientos|Total|Saldo|Productos|Ultimos|Últimos|Acciones)(:.*)?$", re.I)
CLP_RE = re.compile(r"\$\d{1,3}(?:\.\d{3})+")
ALREADY_BOLD_RE = re.compile(r"\*[^*]+\*")


def _bold_clp(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        token = m.group(0)
        return token if ALREADY_BOLD_RE.search(text[max(0, m.start() - 1) : m.end() + 1]) else f"*{token}*"

    return CLP_RE.sub(repl, text)


def _table_to_bullets(lines: List[str]) -> List[str]:
    out: List[str] = []
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        if TABLE_SEP_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0].lower() not in ("empresa", "company", "---"):
            if len(cells) >= 3:
                out.append(f"• {cells[0]} — {cells[2]} ({cells[1]})")
            else:
                out.append(f"• {' — '.join(cells)}")
    return out


def format_whatsapp_reply(text: str) -> str:
    if not text or not text.strip():
        return text

    raw_lines = text.splitlines()
    out: List[str] = []
    table_buf: List[str] = []
    in_table = False

    def flush_table() -> None:
        nonlocal in_table, table_buf
        if table_buf:
            out.extend(_table_to_bullets(table_buf))
            table_buf = []
        in_table = False

    for line in raw_lines:
        stripped = line.strip()
        if stripped.startswith("|"):
            in_table = True
            table_buf.append(line)
            continue
        flush_table()

        hm = HEADER_LINE_RE.match(stripped)
        if hm:
            title = hm.group(1).strip()
            if not title.startswith("*"):
                title = f"*{title}*"
            out.append(title)
            continue

        if stripped in {"---", "───", "—" * 3}:
            out.append("───")
            continue

        if stripped.startswith("```"):
            out.append(stripped.replace("```", ""))
            continue

        if SECTION_RE.match(stripped) and not stripped.startswith("*"):
            out.append(f"*{stripped.rstrip(':')}:*")
            continue

        if stripped.startswith("• ") or stripped.startswith("- "):
            body = stripped[2:].strip()
            out.append(f"• {_bold_clp(body)}")
            continue

        out.append(_bold_clp(line))

    flush_table()
    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
