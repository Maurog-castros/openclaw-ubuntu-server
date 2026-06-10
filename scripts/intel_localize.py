"""Titulos compactos en espanol para Intel Daily (fuentes HN/Reddit/GitHub/LinkedIn)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

ROOT = Path("/home/node/openclaw-mauro") if Path("/home/node/openclaw-mauro").exists() else Path(__file__).resolve().parent.parent
DEFAULT_MAX_TITLE = 72
DEFAULT_MAX_DESC = 95

_SPANISH_HINT = re.compile(
    r"\b(el|la|los|las|de|del|para|con|sin|empresas|herramientas|como|esta|estan|nuevo|nueva)\b|"
    r"[áéíóúñ¿¡]",
    re.I,
)
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "]+",
    flags=re.UNICODE,
)
_BATCH_SIZE = 10


def env_value(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def litellm_url() -> str:
    import os

    if os.environ.get("LITELLM_URL"):
        return os.environ["LITELLM_URL"]
    if Path("/.dockerenv").exists():
        return "http://litellm:4000/v1/chat/completions"
    return "http://127.0.0.1:4000/v1/chat/completions"


def litellm_model() -> str:
    import os

    return os.environ.get("LITELLM_MODEL", "openclaw-remote")


def sanitize_text(text: str) -> str:
    cleaned = _EMOJI_RE.sub("", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def strip_source_title(item: str) -> str:
    text = re.sub(r"\s+", " ", (item or "")).strip()
    if text.startswith("["):
        m = re.match(r"\[([^\]]+)\]", text)
        if m:
            return m.group(1).strip()
    for sep in (" — score:", " — score:", " — "):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
    return text.strip("[] ")


def compact(text: str, max_len: int = DEFAULT_MAX_TITLE) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(".,;:-") + "…"


def is_mostly_spanish(text: str) -> bool:
    return bool(_SPANISH_HINT.search(text))


def master_key() -> str:
    import os

    return (
        os.environ.get("LITELLM_MASTER_KEY", "").strip()
        or env_value(ROOT / "openclaw/.env", "LITELLM_MASTER_KEY")
    )


def _translate_chunk_llm(texts: list[str], *, max_len: int) -> list[str] | None:
    if not texts:
        return []
    key = master_key()
    if not key:
        return None

    clean_texts = [sanitize_text(t) or t for t in texts]
    payload = {
        "model": litellm_model(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "Localizas titulos para un radar diario DevOps/IA en Chile. "
                    "Responde SOLO JSON valido."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Para cada texto, devuelve un titulo en ESPANOL chileno tecnico, "
                    f"resumido y compacto (max {max_len} caracteres). "
                    "Si ya esta en espanol, acortalo si es largo. "
                    "Conserva marcas propias (Kubernetes, Langfuse, Microsoft, Apple, GitHub). "
                    "Sin comillas ni markdown.\n"
                    f'Formato: {{"items": ["...", ...]}} — mismo orden y cantidad ({len(clean_texts)}).\n'
                    f"Entrada: {json.dumps(clean_texts, ensure_ascii=False)}"
                ),
            },
        ],
        "temperature": 0,
        "max_tokens": max(256, 48 * len(clean_texts)),
    }
    req = urllib.request.Request(
        litellm_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return None

    content = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        return None
    try:
        parsed = json.loads(m.group(0))
        items = parsed.get("items")
        if not isinstance(items, list) or len(items) != len(clean_texts):
            return None
        return [compact(str(x), max_len) for x in items]
    except json.JSONDecodeError:
        return None


def _translate_batch_llm(texts: list[str], *, max_len: int) -> list[str]:
    if not texts:
        return []
    out: list[str] = []
    for start in range(0, len(texts), _BATCH_SIZE):
        chunk = texts[start : start + _BATCH_SIZE]
        translated = _translate_chunk_llm(chunk, max_len=max_len)
        if translated is None:
            for text in chunk:
                one = _translate_chunk_llm([text], max_len=max_len)
                out.append(one[0] if one else compact(text, max_len))
        else:
            out.extend(translated)
    return out


class Localizer:
    """Acumula textos y traduce en lote a espanol compacto."""

    def __init__(self, *, max_title: int = DEFAULT_MAX_TITLE, max_desc: int = DEFAULT_MAX_DESC) -> None:
        self.max_title = max_title
        self.max_desc = max_desc
        self._pending: dict[str, int] = {}
        self._cache: dict[str, str] = {}

    def _key(self, text: str, max_len: int) -> str:
        return f"{max_len}:{text}"

    def queue(self, text: str, *, max_len: int | None = None) -> None:
        raw = sanitize_text(text)
        if not raw:
            return
        limit = max_len or self.max_title
        self._pending[self._key(raw, limit)] = limit

    def queue_title(self, text: str) -> None:
        self.queue(strip_source_title(text), max_len=self.max_title)

    def queue_many(self, texts: Iterable[str], *, max_len: int | None = None) -> None:
        for text in texts:
            self.queue(text, max_len=max_len)

    def flush(self) -> None:
        by_limit: dict[int, list[str]] = {}
        for key, limit in self._pending.items():
            if key in self._cache:
                continue
            _, text = key.split(":", 1)
            by_limit.setdefault(limit, []).append(text)

        for limit, texts in by_limit.items():
            unique = list(dict.fromkeys(texts))
            translated = _translate_batch_llm(unique, max_len=limit)
            for src, dst in zip(unique, translated):
                self._cache[self._key(src, limit)] = dst or compact(src, limit)

        self._pending.clear()

    def text(self, raw: str, *, max_len: int | None = None) -> str:
        limit = max_len or self.max_title
        clean = sanitize_text(raw)
        if not clean:
            return ""
        key = self._key(clean, limit)
        if key not in self._cache:
            self.queue(clean, max_len=limit)
            self.flush()
        return self._cache.get(key, compact(clean, limit))

    def title(self, raw: str) -> str:
        return self.text(strip_source_title(raw), max_len=self.max_title)

    def desc(self, raw: str) -> str:
        return self.text(raw, max_len=self.max_desc)
