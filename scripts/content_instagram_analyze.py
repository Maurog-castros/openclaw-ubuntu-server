"""Descarga y analiza un post publico de Instagram (texto + imagen) para inspirar borradores."""

from __future__ import annotations

import argparse
import html as html_module
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from finanzas_common import resolve_data_path

DEFAULT_REF_DIR = "data/workspace/marketing/content/references/instagram"
USER_AGENT = (
    "Mozilla/5.0 (compatible; facebookexternalhit/1.1; +https://openclaw.local/bot)"
)

INSTAGRAM_ANALYZE_PROMPT = """Analiza esta captura de un post de Instagram para usarla como INSPIRACION (no copiar).
Responde SOLO JSON valido:
{
  "hook": "primera linea o gancho visual",
  "estructura": "carrusel|single|video|otro",
  "tema": "tema principal en 1 frase",
  "texto_visible": "caption o texto legible resumido",
  "elementos_visuales": ["lista de elementos en la imagen"],
  "tono": "educativo|motivacional|corporativo|otro",
  "que_funciona": "1-2 frases",
  "adaptacion_mauro": "como adaptarlo a voz DevOps+IA enterprise Chile sin hype"
}
"""


def normalize_instagram_url(url: str) -> str:
    text = (url or "").strip()
    text = text.split("?")[0].rstrip("/")
    match = re.search(r"instagram\.com/(?:p|reel|reels)/([^/]+)", text, re.I)
    if not match:
        raise ValueError(f"URL Instagram no reconocida: {url}")
    shortcode = match.group(1)
    return f"https://www.instagram.com/p/{shortcode}/"


def shortcode_from_url(post_url: str) -> str:
    match = re.search(r"/(?:p|reel|reels)/([^/?#]+)", post_url, re.I)
    if not match:
        raise ValueError(f"shortcode no encontrado en {post_url}")
    return match.group(1)


def fetch_embed_html(post_url: str) -> str:
    shortcode = shortcode_from_url(post_url)
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    req = urllib.request.Request(embed_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def decode_json_string(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        pass
    try:
        return bytes(raw, "utf-8").decode("unicode_escape")
    except Exception:
        return raw.replace("\\n", "\n").replace("\\/", "/")


def extract_caption_from_embed_html(html: str) -> str:
    """Caption en embed /captioned/ (HTML, sin edge_media_to_caption en JSON)."""
    for pattern in (
        r'captionProfileClick"[^>]*>[^<]+</a>(?:<br\s*/>)+(.+?)<div class="CaptionComments"',
        r'CaptionUsername"[^>]*>[^<]+</a>(?:<br\s*/>)+(.+?)<div class="CaptionComments"',
    ):
        match = re.search(pattern, html, re.I | re.S)
        if not match:
            continue
        block = match.group(1)
        block = re.sub(r"<br\s*/>", "\n", block, flags=re.I)
        block = re.sub(r"<[^>]+>", "", block)
        text = html_module.unescape(block).strip()
        if text:
            return text
    return ""


def extract_author_from_embed_html(html: str) -> str:
    match = re.search(r"user\?username=([a-zA-Z0-9._]+)", html)
    if match:
        return match.group(1)
    match = re.search(
        r'instagram\.com/([a-zA-Z0-9._]+)/\?[^"]*utm_source=ig_embed',
        html,
        re.I,
    )
    if match:
        return match.group(1)
    return ""


def extract_caption_from_embed(html: str) -> str:
    html_caption = extract_caption_from_embed_html(html)
    if html_caption:
        return html_caption

    anchor = html.find("edge_media_to_caption")
    if anchor < 0:
        for pattern in (
            r'"caption":"((?:\\.|[^"\\])*)"',
            r'"caption_text":"((?:\\.|[^"\\])*)"',
        ):
            match = re.search(pattern, html)
            if match:
                return decode_json_string(match.group(1)).strip()
        return ""

    chunk = html[anchor : anchor + 8000]
    marker = 'text\\":\\"'
    start = chunk.find(marker)
    if start < 0:
        marker = '"text":"'
        start = chunk.find(marker)
        if start < 0:
            return ""
        start += len(marker)
        end = chunk.find('"', start)
        raw = chunk[start:end]
    else:
        start += len(marker)
        end = chunk.find('\\"', start)
        raw = chunk[start:end]
    if "\\\\u" in raw or "\\\\n" in raw:
        raw = raw.replace("\\\\", "\\")
    try:
        return json.loads(f'"{raw}"').strip()
    except json.JSONDecodeError:
        return decode_json_string(raw).strip()


def is_post_media_url(url: str) -> bool:
    lowered = url.lower()
    if any(lowered.endswith(ext) for ext in (".js", ".css", ".woff2", ".woff", ".html")):
        return False
    if "rsrc.php" in lowered or "/static/" in lowered:
        return False
    return any(
        token in lowered
        for token in (
            "scontent",
            "cdninstagram.com/v/t",
            "lookaside.instagram.com",
            "fbcdn.net/v/t",
        )
    )


def extract_image_urls_from_embed(html: str) -> List[str]:
    images: List[str] = []
    for pattern in (
        r'display_url\\":\\"(https:[^\\]+)',
        r'"display_url":"(https://[^"]+)"',
        r'\\"src\\":\\"(https:[^\\]+)',
        r'"src":"(https://[^"]+)"',
    ):
        for match in re.finditer(pattern, html):
            url = match.group(1).replace("\\/", "/").replace("\\u0026", "&")
            if is_post_media_url(url):
                images.append(url)
    norm = html.replace("\\/", "/")
    for url in re.findall(r'"display_url":"(https://[^"]+)"', norm):
        if is_post_media_url(url):
            images.append(url)
    seen = set()
    unique: List[str] = []
    for img in images:
        if img not in seen:
            seen.add(img)
            unique.append(img)
    return unique


def extract_from_embed(html: str) -> Dict[str, Any]:
    caption = extract_caption_from_embed(html)
    unique_images = extract_image_urls_from_embed(html)

    author = extract_author_from_embed_html(html)
    if not author:
        for pattern in (r'"username":"([^"]+)"', r'\\"username\\":\\"([^\\"]+)\\"'):
            author_match = re.search(pattern, html)
            if author_match:
                author = author_match.group(1)
                break

    return {
        "caption": caption,
        "author": author,
        "image_urls": unique_images[:10],
    }


def download_image(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    dest.write_bytes(data)
    return dest


def try_oembed(post_url: str) -> Dict[str, Any]:
    api = f"https://api.instagram.com/oembed?url={urllib.request.quote(post_url, safe='')}"
    req = urllib.request.Request(api, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {
            "title": data.get("title") or "",
            "author_name": data.get("author_name") or "",
            "thumbnail_url": data.get("thumbnail_url") or "",
        }
    except Exception:
        return {}


def analyze_image_vision(image_path: Path, model: str) -> Dict[str, Any]:
    try:
        from receipt_vision_agent import call_vision_model, extract_json_object, openclaw_client
    except ImportError as exc:
        return {"error": f"vision_no_disponible: {exc}"}

    client = openclaw_client()
    raw = call_vision_model(client, model, image_path, INSTAGRAM_ANALYZE_PROMPT)
    parsed = extract_json_object(raw)
    if isinstance(parsed, dict):
        return parsed
    return {"raw_analysis": raw}


def _caption_excerpt(caption: str, limit: int = 420) -> str:
    text = (caption or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def build_whatsapp_reply(payload: Dict[str, Any]) -> str:
    """Texto listo para enviar por WhatsApp (sin meta-instrucciones)."""
    author = payload.get("author") or payload.get("oembed", {}).get("author_name") or "desconocido"
    url = payload.get("url", "")
    vision = payload.get("vision_analysis") or {}
    caption = payload.get("caption") or ""

    lines = [f"Revisé el post de @{author} (Instagram)", ""]

    if vision and not vision.get("error"):
        if vision.get("estructura"):
            lines.append(f"Formato: {vision['estructura']}")
        if vision.get("hook"):
            lines.append(f"Gancho: {vision['hook']}")
        if vision.get("tema"):
            lines.append(f"Tema: {vision['tema']}")
        if vision.get("que_funciona"):
            lines.append(f"Qué funciona: {vision['que_funciona']}")
        if vision.get("adaptacion_mauro"):
            lines.append("")
            lines.append(f"Para tu voz (DevOps+IA Chile): {vision['adaptacion_mauro']}")
    else:
        excerpt = _caption_excerpt(caption)
        if excerpt:
            lines.append("De qué va (resumen del caption):")
            lines.append(excerpt)
        lines.append("")
        lines.append(
            "Formato típico: lista de noticias positivas con emojis por ítem (viral informativo, no enterprise)."
        )

    lines.append("")
    lines.append(
        "¿Quieres que arme un post nuevo inspirado en este estilo para tu marca (agentes IA / DevOps), "
        "sin copiar el contenido? Responde sí y el ángulo, o pide cambios."
    )
    if url:
        lines.append("")
        lines.append(f"Ref: {url}")
    return "\n".join(lines)


def build_summary(payload: Dict[str, Any]) -> str:
    lines = [
        f"=== Inspiracion Instagram ===",
        f"URL: {payload.get('url', '')}",
        f"Autor: {payload.get('author') or payload.get('oembed', {}).get('author_name', '')}",
        "",
    ]
    caption = payload.get("caption") or payload.get("oembed", {}).get("title") or ""
    if caption:
        lines.append("Caption / texto:")
        lines.append(caption[:1200])
        lines.append("")
    vision = payload.get("vision_analysis") or {}
    if vision and not vision.get("error"):
        lines.append("Analisis visual:")
        for key in ("tema", "estructura", "hook", "que_funciona", "adaptacion_mauro"):
            if vision.get(key):
                lines.append(f"- {key}: {vision[key]}")
        elems = vision.get("elementos_visuales") or []
        if elems:
            lines.append("- elementos: " + ", ".join(str(e) for e in elems[:8]))
    lines.append("")
    lines.append(
        "Siguiente: content_draft_instagram.py --topic \"...\" --brief \"<adaptacion>\" "
        "o pedir borrador nuevo inspirado en esto."
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analiza post Instagram publico.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--refs-dir", default=DEFAULT_REF_DIR)
    parser.add_argument("--vision-model", default="openclaw-remote-vision")
    parser.add_argument("--no-vision", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    post_url = normalize_instagram_url(args.url)
    shortcode = shortcode_from_url(post_url)
    refs_dir = resolve_data_path(args.refs_dir)
    refs_dir.mkdir(parents=True, exist_ok=True)

    oembed = try_oembed(post_url)
    try:
        html = fetch_embed_html(post_url)
        extracted = extract_from_embed(html)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"No se pudo cargar embed Instagram: HTTP {exc.code}") from exc

    image_paths: List[str] = []
    urls = extracted.get("image_urls") or []
    if not urls and oembed.get("thumbnail_url"):
        urls = [oembed["thumbnail_url"]]

    for idx, img_url in enumerate(urls[:3]):
        ext = ".jpg" if ".jpg" in img_url.lower() else ".png"
        path = refs_dir / f"{shortcode}-{idx + 1}{ext}"
        try:
            download_image(img_url, path)
            image_paths.append(str(path))
        except Exception:
            continue

    vision: Dict[str, Any] = {}
    if image_paths and not args.no_vision:
        vision = analyze_image_vision(Path(image_paths[0]), args.vision_model)

    payload: Dict[str, Any] = {
        "status": "ok",
        "url": post_url,
        "shortcode": shortcode,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "author": extracted.get("author") or oembed.get("author_name", ""),
        "caption": extracted.get("caption") or oembed.get("title", ""),
        "image_paths": image_paths,
        "oembed": oembed,
        "vision_analysis": vision,
        "summary": "",
        "whatsapp_reply": "",
    }
    payload["summary"] = build_summary(payload)
    payload["whatsapp_reply"] = build_whatsapp_reply(payload)

    meta_path = refs_dir / f"{shortcode}.json"
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["meta_path"] = str(meta_path)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["summary"])


if __name__ == "__main__":
    main()
