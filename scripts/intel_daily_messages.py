"""Build and optionally send grouped Intel Daily WhatsApp messages."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from intel_daily_report import RAW, ROOT, build_report, bullets, format_whatsapp, github_topics, refresh_sources, section, top_relevant
from intel_localize import Localizer

DEFAULT_TARGET_FILE = Path("/home/node/.openclaw-secrets/whatsapp_allow_from.txt")


def fmt_item(item: str, loc: Localizer) -> str:
    title = loc.title(item)
    score_match = re.search(r"score:([0-9]+)", item)
    comments_match = re.search(r"comments:([0-9]+)", item)
    metric = ""
    if score_match:
        metric = f" — {score_match.group(1)} pts HN"
        if comments_match:
            metric += f", {comments_match.group(1)} comentarios"
    return f"• {title}{metric}"


def build_messages(raw: str) -> list[str]:
    hn_items = top_relevant(bullets(section(raw, "# Hacker News Top 20", ["## Reddit"])), 8)
    reddit_items = top_relevant(bullets(section(raw, "## Reddit", ["## GitHub Trending", "## GitHub Topics"])), 10)
    repos = github_topics(raw)

    loc = Localizer()
    for item in hn_items[:7] + reddit_items[:8]:
        loc.queue_title(item)
    for repo in repos[:8]:
        loc.queue(repo["desc"], max_len=120)
    loc.flush()

    hn_body = "\n".join(fmt_item(item, loc) for item in hn_items[:7]) or "• Sin senales HN relevantes hoy."
    hn_msg = "🔥 *Intel Daily - Hacker News*\n\n" + hn_body

    reddit_body = "\n".join(fmt_item(item, loc) for item in reddit_items[:8]) or "• Sin senales Reddit relevantes hoy."
    reddit_msg = "🧵 *Intel Daily - Reddit*\n\n" + reddit_body

    github_lines = [
        f"• *{repo['name']}* ({repo['stars']} estrellas): {loc.text(repo['desc'], max_len=120)}"
        for repo in repos[:8]
    ]
    github_body = "\n".join(github_lines) if github_lines else "• Sin señales GitHub relevantes hoy."
    github_msg = "💻 *Intel Daily - GitHub*\n\n" + github_body

    final = format_whatsapp(build_report(raw))
    final = final.replace("🧭 *Intel Daily Consolidado", "🧭 *Intel Daily - Sintesis final")
    return [hn_msg, reddit_msg, github_msg, final]


def truncate_message(message: str) -> str:
    message = message.strip()
    if len(message) <= 3900:
        return message
    return message[:3800].rstrip() + "\n\n(Truncado; ver reporte local completo.)"


def send_whatsapp(messages: list[str], target_file: str) -> list[dict[str, object]]:
    target = Path(target_file).read_text(encoding="utf-8").strip().splitlines()[0]
    sent = []
    for index, message in enumerate(messages, start=1):
        proc = subprocess.run(
            [
                "openclaw", "message", "send",
                "--channel", "whatsapp", "--target", target,
                "--message", truncate_message(message), "--json",
            ],
            cwd=str(ROOT), text=True, capture_output=True, timeout=90, check=False,
        )
        sent.append({"index": index, "ok": proc.returncode == 0, "stdout": proc.stdout[-800:], "stderr": proc.stderr[-800:]})
    return sent


def main() -> None:
    parser = argparse.ArgumentParser(description="Build grouped Intel Daily messages.")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--send-whatsapp", action="store_true")
    parser.add_argument("--target-file", default=str(DEFAULT_TARGET_FILE))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.refresh:
        refresh_sources()

    raw = RAW.read_text(encoding="utf-8")
    messages = build_messages(raw)
    payload: dict[str, object] = {
        "status": "ok",
        "message_count": len(messages),
        "whatsapp_messages": messages,
        "whatsapp_reply": f"Intel Daily enviado en {len(messages)} mensajes: HN, Reddit, GitHub y sintesis final.",
    }

    if args.send_whatsapp:
        sent = send_whatsapp(messages, args.target_file)
        payload["sent"] = sent
        if not all(item.get("ok") for item in sent):
            payload["status"] = "error"
            payload["whatsapp_reply"] = "Intel Daily genero mensajes, pero fallo uno o mas envios por WhatsApp."

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("\n\n---\n\n".join(messages))


if __name__ == "__main__":
    main()
