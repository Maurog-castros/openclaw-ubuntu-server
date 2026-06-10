"""Stress test LiteLLM -> ia.iamiko.cl -> qwen3-coder-next."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
API_URL = os.environ.get("LITELLM_URL", "http://127.0.0.1:4000/v1/chat/completions")
MODEL = os.environ.get("LITELLM_MODEL", "openclaw-remote")


def env_value(path: Path, key: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def call_model(name: str, prompt: str, *, max_tokens: int = 128) -> dict[str, Any]:
    master_key = env_value(ROOT / "openclaw/.env", "LITELLM_MASTER_KEY")
    body = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Responde breve. Devuelve solo resultado solicitado.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    started = time.perf_counter()
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {master_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=220) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elapsed = round(time.perf_counter() - started, 2)
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {
            "name": name,
            "ok": True,
            "seconds": elapsed,
            "chars_in": len(prompt),
            "chars_out": len(content),
            "finish_reason": data.get("choices", [{}])[0].get("finish_reason"),
            "usage": data.get("usage", {}),
            "sample": re.sub(r"\s+", " ", content)[:180],
        }
    except urllib.error.HTTPError as exc:
        return {
            "name": name,
            "ok": False,
            "seconds": round(time.perf_counter() - started, 2),
            "status": exc.code,
            "error": exc.read().decode("utf-8", errors="ignore")[:800],
        }
    except Exception as exc:
        return {
            "name": name,
            "ok": False,
            "seconds": round(time.perf_counter() - started, 2),
            "error": str(exc),
        }


def long_prompt(lines: int) -> str:
    block = "\n".join(
        f"{i:05d}: container ETA validation, BL tracking, Santander receipt reconciliation."
        for i in range(lines)
    )
    return (
        "Lee contexto largo. Responde JSON compacto con keys line_count, first, last.\n"
        f"{block}\n"
        "Usa solo datos del contexto."
    )


def main() -> None:
    tests = [
        ("small", "Responde: ok qwen3-coder-next operativo", 32),
        ("medium_8k_chars", long_prompt(120), 96),
        ("long_55k_chars", long_prompt(800), 128),
    ]
    results = [call_model(name, prompt, max_tokens=max_tokens) for name, prompt, max_tokens in tests]

    concurrent: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(call_model, f"parallel_{i}", f"Calcula {i}+{i}; responde solo numero.", max_tokens=16)
            for i in range(1, 5)
        ]
        for future in as_completed(futures):
            concurrent.append(future.result())

    payload = {
        "model": MODEL,
        "api_url": API_URL,
        "serial": results,
        "parallel": sorted(concurrent, key=lambda item: item["name"]),
        "ok": all(item.get("ok") for item in results + concurrent),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
