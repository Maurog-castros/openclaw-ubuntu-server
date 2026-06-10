"""YouTube → resumen, debate e insights para agente Intel."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/home/node/openclaw-mauro") if Path("/home/node/openclaw-mauro").exists() else Path(__file__).resolve().parent.parent
INTEL_WS = ROOT / "data/workspace/marketing/intel"
YT_DIR = INTEL_WS / "youtube"
SUMMARIES = YT_DIR / "summaries"
SESSIONS = YT_DIR / "sessions"
INSIGHTS_JSONL = YT_DIR / "insights.jsonl"
INSIGHTS_MD = INTEL_WS / "insights/youtube.md"
SESSION_STATE = ROOT / "data/intel_youtube_session.json"
SESSION_TTL_SEC = 2 * 60 * 60

YOUTUBE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:"
    r"youtube\.com/watch\?(?:[^&\s]+&)*v=|youtube\.com/watch\?v=|"
    r"youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/"
    r")([a-zA-Z0-9_-]{11})",
    re.I,
)
INSIGHT_CMD_RE = re.compile(
    r"^\s*(?:registra(?:r)?|guarda(?:r)?)\s+insight\s*:\s*(.+)$",
    re.I | re.S,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def extract_video_id(text: str) -> str | None:
    m = YOUTUBE_URL_RE.search(text or "")
    return m.group(1) if m else None


def fetch_oembed(video_id: str) -> dict[str, str]:
    url = f"https://www.youtube.com/watch?v={video_id}"
    api = "https://www.youtube.com/oembed?" + urllib.parse.urlencode({"url": url, "format": "json"})
    try:
        with urllib.request.urlopen(api, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {
            "title": str(data.get("title") or video_id),
            "author": str(data.get("author_name") or ""),
            "url": url,
        }
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return {"title": video_id, "author": "", "url": url}


def _snippet_text(chunk: Any) -> str:
    if isinstance(chunk, dict):
        return str(chunk.get("text") or "")
    return str(getattr(chunk, "text", chunk) or "")


def fetch_transcript(video_id: str) -> tuple[str, str]:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise RuntimeError(
            "Falta youtube-transcript-api. Instala: pip install youtube-transcript-api"
        ) from exc

    api = YouTubeTranscriptApi()
    langs = ["es", "es-419", "en", "en-US"]
    lang_used = "auto"
    chunks: list[Any] = []
    try:
        fetched = api.fetch(video_id, languages=langs)
        chunks = list(fetched)
        lang_used = str(getattr(fetched, "language_code", None) or getattr(fetched, "language", "auto"))
    except Exception:
        listing = api.list(video_id)
        tr = listing.find_transcript(langs)
        chunks = list(tr.fetch())
        lang_used = str(getattr(tr, "language_code", None) or getattr(tr, "language", "auto"))

    text = re.sub(r"\s+", " ", " ".join(_snippet_text(c) for c in chunks)).strip()
    if not text:
        raise RuntimeError("Transcripcion vacia o no disponible para este video.")
    return text, lang_used


def llm_chat(system: str, user: str, *, max_tokens: int = 1200) -> str:
    from intel_localize import litellm_model, litellm_url, master_key

    key = master_key()
    if not key:
        raise RuntimeError("LITELLM_MASTER_KEY no configurada.")

    payload = {
        "model": litellm_model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        litellm_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return str((body.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()


def chunk_text(text: str, size: int = 9000) -> list[str]:
    if len(text) <= size:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        parts.append(text[start : start + size])
        start += size
    return parts


def summarize_transcript(meta: dict[str, str], transcript: str, lang: str) -> dict[str, Any]:
    system = (
        "Eres Intel, scout DevOps/IA para Mauro (Chile). "
        "Responde SOLO JSON valido en espanol chileno tecnico."
    )
    chunks = chunk_text(transcript)
    partials: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks, 1):
        user = (
            f"Video: {meta['title']} | Canal: {meta['author']} | URL: {meta['url']}\n"
            f"Idioma transcripcion: {lang} | Parte {i}/{len(chunks)}\n\n"
            f"Extrae JSON con keys: key_points (lista 3-6 strings cortos), "
            f"insights_mauro (lista 2-4 aplicables a consultoria DevOps/IA Chile), "
            f"actionables (lista 1-3), quotes (lista 0-2 citas textuales cortas opcional).\n\n"
            f"TRANSCRIPCION:\n{chunk}"
        )
        raw = llm_chat(system, user, max_tokens=900)
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            continue
        try:
            partials.append(json.loads(m.group(0)))
        except json.JSONDecodeError:
            continue

    merged: dict[str, Any] = {
        "key_points": [],
        "insights_mauro": [],
        "actionables": [],
        "quotes": [],
    }
    for part in partials:
        for key in merged:
            for item in part.get(key) or []:
                s = str(item).strip()
                if s and s not in merged[key]:
                    merged[key].append(s)

    if not merged["key_points"]:
        merged["key_points"] = ["No se pudo extraer puntos estructurados; revisar transcripcion manual."]

    if len(chunks) > 1:
        merge_user = (
            f"Consolida en JSON final (mismas keys, max 6 key_points, 4 insights, 3 actionables):\n"
            f"{json.dumps(merged, ensure_ascii=False)}"
        )
        raw = llm_chat(system, merge_user, max_tokens=700)
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                merged = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

    merged["title"] = meta["title"]
    merged["author"] = meta["author"]
    merged["url"] = meta["url"]
    merged["transcript_lang"] = lang
    merged["word_count"] = len(transcript.split())
    return merged


def format_whatsapp_summary(data: dict[str, Any], *, summary_path: str) -> str:
    lines = [
        f"🎬 *YouTube Intel — {data.get('title', 'Video')}*",
        f"Canal: {data.get('author') or '—'}",
        f"🔗 {data.get('url', '')}",
        "",
        "📌 *Puntos clave*",
    ]
    for i, point in enumerate(data.get("key_points") or [], 1):
        lines.append(f"{i}. {point}")
    lines += ["", "💡 *Insights para ti (DevOps/IA Chile)*"]
    for item in data.get("insights_mauro") or []:
        lines.append(f"• {item}")
    if data.get("actionables"):
        lines += ["", "🎯 *Accionables*"]
        for item in data["actionables"]:
            lines.append(f"• {item}")
    lines += [
        "",
        "───",
        "_Debate:_ preguntame lo que quieras sobre el video.",
        '_Registrar:_ `registra insight: <tu idea>`_',
        f"_Guardado:_ `{summary_path}`",
    ]
    return "\n".join(lines)


def save_session(video_id: str, data: dict[str, Any], transcript: str) -> Path:
    SESSIONS.mkdir(parents=True, exist_ok=True)
    path = SESSIONS / f"{video_id}.json"
    payload = {
        "video_id": video_id,
        "updated_at": now_iso(),
        "summary": data,
        "transcript_excerpt": transcript[:12000],
        "insights": [],
        "debate_log": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def save_summary_markdown(video_id: str, data: dict[str, Any]) -> Path:
    SUMMARIES.mkdir(parents=True, exist_ok=True)
    path = SUMMARIES / f"{date.today().isoformat()}-{video_id}.md"
    lines = [
        f"# YouTube Intel — {data.get('title')}",
        "",
        f"- **Canal:** {data.get('author')}",
        f"- **URL:** {data.get('url')}",
        f"- **Fecha:** {date.today().isoformat()}",
        f"- **Idioma transcript:** {data.get('transcript_lang')}",
        "",
        "## Puntos clave",
        "",
    ]
    lines += [f"{i}. {p}" for i, p in enumerate(data.get("key_points") or [], 1)]
    lines += ["", "## Insights Mauro", ""]
    lines += [f"- {x}" for x in data.get("insights_mauro") or []]
    lines += ["", "## Accionables", ""]
    lines += [f"- {x}" for x in data.get("actionables") or []]
    if data.get("quotes"):
        lines += ["", "## Citas", ""]
        lines += [f"> {q}" for q in data["quotes"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def set_active_session(video_id: str, session_key: str) -> None:
    SESSION_STATE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_STATE.write_text(
        json.dumps(
            {
                "video_id": video_id,
                "session_key": session_key,
                "updated_at_ts": time.time(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def load_active_session() -> dict[str, Any] | None:
    if not SESSION_STATE.exists():
        return None
    try:
        data = json.loads(SESSION_STATE.read_text(encoding="utf-8"))
        if time.time() - float(data.get("updated_at_ts") or 0) > SESSION_TTL_SEC:
            return None
        vid = data.get("video_id")
        if vid and (SESSIONS / f"{vid}.json").exists():
            return data
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def load_video_session(video_id: str) -> dict[str, Any]:
    path = SESSIONS / f"{video_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No hay sesion previa para {video_id}. Pasa el link primero.")
    return json.loads(path.read_text(encoding="utf-8"))


def persist_session(video_id: str, session: dict[str, Any]) -> None:
    session["updated_at"] = now_iso()
    (SESSIONS / f"{video_id}.json").write_text(
        json.dumps(session, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def register_insight(video_id: str, insight: str, session: dict[str, Any]) -> str:
    insight = insight.strip()
    if not insight:
        raise ValueError("Insight vacio.")
    summary = session.get("summary") or {}
    record = {
        "ts": now_iso(),
        "video_id": video_id,
        "title": summary.get("title", ""),
        "url": summary.get("url", ""),
        "insight": insight,
    }
    INSIGHTS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with INSIGHTS_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    INSIGHTS_MD.parent.mkdir(parents=True, exist_ok=True)
    block = (
        f"\n## {record['ts'][:10]} — {summary.get('title', video_id)}\n"
        f"- URL: {summary.get('url', '')}\n"
        f"- Insight: {insight}\n"
    )
    if INSIGHTS_MD.exists():
        INSIGHTS_MD.write_text(INSIGHTS_MD.read_text(encoding="utf-8") + block, encoding="utf-8")
    else:
        INSIGHTS_MD.write_text("# Insights YouTube (Intel)\n" + block, encoding="utf-8")

    session.setdefault("insights", []).append(record)
    persist_session(video_id, session)
    return insight


def run_summarize(url_or_id: str) -> dict[str, Any]:
    video_id = extract_video_id(url_or_id) or (url_or_id if re.fullmatch(r"[a-zA-Z0-9_-]{11}", url_or_id) else None)
    if not video_id:
        raise ValueError("URL de YouTube invalida.")

    meta = fetch_oembed(video_id)
    transcript, lang = fetch_transcript(video_id)
    summary = summarize_transcript(meta, transcript, lang)
    md_path = save_summary_markdown(video_id, summary)
    save_session(video_id, summary, transcript)
    session_key = f"agent:intel:youtube:{video_id}"
    set_active_session(video_id, session_key)

    return {
        "status": "ok",
        "agent": "intel",
        "video_id": video_id,
        "session_key": session_key,
        "summary_file": str(md_path),
        "session_file": str(SESSIONS / f"{video_id}.json"),
        "summary": summary,
        "whatsapp_reply": format_whatsapp_summary(summary, summary_path=str(md_path)),
    }


def run_debate(video_id: str, message: str) -> dict[str, Any]:
    session = load_video_session(video_id)
    summary = session.get("summary") or {}
    set_active_session(video_id, f"agent:intel:youtube:{video_id}")

    m = INSIGHT_CMD_RE.match(message or "")
    if m:
        insight = register_insight(video_id, m.group(1), session)
        return {
            "status": "ok",
            "agent": "intel",
            "video_id": video_id,
            "registered_insight": insight,
            "whatsapp_reply": f"✅ Insight registrado:\n*{insight}*\n\nVer `{INSIGHTS_MD}`",
        }

    system = (
        "Eres Intel debatiendo un video de YouTube con Mauro (arquitecto DevOps/IA, Chile). "
        "Conoces el resumen y la transcripcion parcial. Responde en espanol chileno, "
        "tecnico y directo (max 12 lineas para WhatsApp). Cuestiona supuestos, conecta con "
        "oportunidades de consultoria/producto/contenido. Si Mauro tiene razon, reconocelo. "
        "Si pide registrar un insight, dile que use: registra insight: <texto>."
    )
    context = (
        f"TITULO: {summary.get('title')}\nURL: {summary.get('url')}\n"
        f"PUNTOS: {json.dumps(summary.get('key_points'), ensure_ascii=False)}\n"
        f"INSIGHTS PREVIOS: {json.dumps(session.get('insights'), ensure_ascii=False)}\n"
        f"TRANSCRIPT EXCERPT:\n{session.get('transcript_excerpt', '')[:6000]}\n"
    )
    reply = llm_chat(system, f"CONTEXTO VIDEO:\n{context}\n\nMENSAJE MAURO:\n{message}", max_tokens=500)

    session.setdefault("debate_log", []).append({"ts": now_iso(), "user": message, "reply": reply})
    persist_session(video_id, session)

    return {
        "status": "ok",
        "agent": "intel",
        "video_id": video_id,
        "whatsapp_reply": reply,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Intel YouTube: resumen, debate e insights.")
    parser.add_argument("--url", default="", help="URL o video_id de YouTube")
    parser.add_argument("--text", default="", help="Mensaje de debate o registra insight:")
    parser.add_argument("--video-id", default="", help="ID para debate sin URL")
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--debate", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        if args.summarize or (args.url and not args.debate):
            payload = run_summarize(args.url)
        elif args.debate or args.text:
            active = load_active_session()
            vid = args.video_id or (active or {}).get("video_id") or extract_video_id(args.url)
            if not vid:
                raise ValueError("Sin sesion YouTube activa. Pasa un link primero.")
            payload = run_debate(vid, args.text or args.url)
        else:
            raise ValueError("Usa --url con --summarize o --debate --text")
    except Exception as exc:
        payload = {
            "status": "error",
            "agent": "intel",
            "whatsapp_reply": f"YouTube Intel: {exc}",
        }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload.get("whatsapp_reply", ""))


if __name__ == "__main__":
    main()
