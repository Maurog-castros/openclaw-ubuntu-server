#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/mauro/openclaw-mauro"
OPENCLAW_DIR="$ROOT/openclaw"
CONFIG_JSON="$ROOT/data/config/openclaw.json"
LITELLM_CONFIG="$OPENCLAW_DIR/litellm-config.yaml"
OPENWEBUI_DB="/app/backend/data/webui.db"
MODELS_URL="${MODELS_URL:-https://ia.iamiko.cl/v1/models}"
CRON_MARKER="# openclaw-model-sync"
CRON_CMD="17 3 * * * flock -n /tmp/openclaw-model-sync.lock $ROOT/scripts/sync-openclaw-models.sh >> $ROOT/logs/model-sync.log 2>&1 $CRON_MARKER"

install_cron() {
  mkdir -p "$ROOT/logs"
  current="$(crontab -l 2>/dev/null || true)"
  filtered="$(printf '%s\n' "$current" | grep -vF "$CRON_MARKER" || true)"
  printf '%s\n%s\n' "$filtered" "$CRON_CMD" | sed '/^$/d' | crontab -
}

if [[ "${1:-}" == "--install-cron" ]]; then
  install_cron
fi

python3 - <<'PY'
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path("/home/mauro/openclaw-mauro")
OPENCLAW_DIR = ROOT / "openclaw"
ENV_FILE = OPENCLAW_DIR / ".env"
CONFIG_JSON = ROOT / "data/config/openclaw.json"
LITELLM_CONFIG = OPENCLAW_DIR / "litellm-config.yaml"
ROUTING_STATE = ROOT / "data/config/model-routing.json"
OPENWEBUI_DB = Path("/app/backend/data/webui.db")
MODELS_URL = os.environ.get("MODELS_URL", "https://ia.iamiko.cl/v1/models")


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def fetch_models() -> list[str]:
    with urllib.request.urlopen(MODELS_URL, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    ids = [item["id"] for item in payload.get("data", []) if item.get("id")]
    return sorted(dict.fromkeys(ids))


def is_embedding(model_id: str) -> bool:
    lowered = model_id.lower()
    return "embed" in lowered or "embedding" in lowered


def pick_model(models: list[str], needles: tuple[str, ...]) -> str | None:
    for needle in needles:
        for model_id in models:
            if needle in model_id.lower():
                return model_id
    return models[0] if models else None


def backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, path.with_suffix(path.suffix + f".bak-{stamp}"))


def write_litellm(env: dict[str, str], text_model: str, vision_model: str | None, embedding_model: str | None) -> list[str]:
    aliases: list[tuple[str, str, int]] = [
        ("openclaw-remote", text_model, 60),
        ("openclaw-remote-coder", text_model, 60),
    ]
    if vision_model:
        aliases.append(("openclaw-remote-vision", vision_model, 60))
    if embedding_model:
        aliases.append(("openclaw-remote-embed", embedding_model, 45))

    lines = ["model_list:"]
    for alias, upstream_model, timeout in aliases:
        lines.extend(
            [
                f"  - model_name: {alias}",
                "    litellm_params:",
                f"      model: openai/{upstream_model}",
                "      api_base: https://ia.iamiko.cl/v1",
                "      api_key: os.environ/OPENAI_API_KEY",
                f"      timeout: {timeout}",
                "",
            ]
        )

    fallbacks = ["openclaw-remote-coder"]
    if vision_model:
        fallbacks.append("openclaw-remote-vision")

    lines.extend(
        [
            "litellm_settings:",
            "  num_retries: 3",
            "  request_timeout: 90",
            "  fallbacks:",
            f"    - openclaw-remote: [{', '.join(fallbacks)}]",
            "    - openclaw-remote-coder: [openclaw-remote]",
            "general_settings:",
            "  master_key: os.environ/LITELLM_MASTER_KEY",
            "",
        ]
    )

    backup(LITELLM_CONFIG)
    LITELLM_CONFIG.write_text("\n".join(lines), encoding="utf-8")
    return [alias for alias, _, _ in aliases]


def model_entry(alias: str, name: str, context_window: int = 32768, max_tokens: int = 4096) -> dict[str, Any]:
    return {
        "id": alias,
        "name": name,
        "reasoning": False,
        "input": ["text"],
        "cost": {
            "input": 0,
            "output": 0,
            "cacheRead": 0,
            "cacheWrite": 0,
        },
        "contextWindow": context_window,
        "maxTokens": max_tokens,
    }


def normalize_agent_models(aliases: list[str], models: dict[str, Any]) -> dict[str, Any]:
    primary = "remote-lm/openclaw-remote"
    fallback_values = ["remote-lm/openclaw-remote-coder"]
    if "openclaw-remote-vision" in aliases:
        fallback_values.append("remote-lm/openclaw-remote-vision")

    models["primary"] = primary
    models["fallbacks"] = fallback_values
    return models


def write_openclaw_config(aliases: list[str], selected: dict[str, str | None]) -> None:
    if not CONFIG_JSON.exists():
        return

    backup(CONFIG_JSON)
    data = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
    if isinstance(data.get("meta"), dict):
        data["meta"].pop("modelSync", None)

    agents = data.setdefault("agents", {})
    defaults = agents.setdefault("defaults", {})
    defaults["model"] = normalize_agent_models(aliases, defaults.get("model") or {})

    for agent in agents.get("list", []):
        if isinstance(agent, dict):
            agent["model"] = normalize_agent_models(aliases, agent.get("model") or {})

    remote_provider = data.setdefault("models", {}).setdefault("providers", {}).get("remote-lm", {})
    provider_models = [
        model_entry("openclaw-remote", f"{selected['text']} via Iamiko (LiteLLM)"),
        model_entry("openclaw-remote-coder", f"{selected['text']} coder via Iamiko (LiteLLM)"),
    ]
    if "openclaw-remote-vision" in aliases and selected.get("vision"):
        provider_models.append(
            model_entry("openclaw-remote-vision", f"{selected['vision']} vision via Iamiko (LiteLLM)")
        )
    if "openclaw-remote-embed" in aliases and selected.get("embedding"):
        provider_models.append(
            model_entry("openclaw-remote-embed", f"{selected['embedding']} embeddings via Iamiko (LiteLLM)", 8192, 8192)
        )

    data["models"]["providers"] = {
        "remote-lm": {
            "baseUrl": remote_provider.get("baseUrl", "http://litellm:4000/v1"),
            "apiKey": remote_provider.get("apiKey", "sk-openclaw-local"),
            "api": remote_provider.get("api", "openai-completions"),
            "timeoutSeconds": remote_provider.get("timeoutSeconds", 60),
            "models": provider_models,
        }
    }

    CONFIG_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sync_openwebui(env: dict[str, str], aliases: list[str], upstream_ids: list[str]) -> None:
    api_key = env.get("LITELLM_MASTER_KEY", "sk-openclaw-local")
    webui_aliases = [alias for alias in aliases if not alias.endswith("-embed")]
    allowed = set(webui_aliases) | set(upstream_ids)

    code = f"""
import json, sqlite3, time
db = {OPENWEBUI_DB.as_posix()!r}
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row
row = con.execute('select * from config order by id limit 1').fetchone()
if row:
    data = json.loads(row['data'])
    config_id = row['id']
else:
    data = {{'version': 0}}
    config_id = 1
data.setdefault('ui', {{}})['enable_signup'] = False
data['openai'] = {{
    'enable': True,
    'api_base_urls': ['http://host.docker.internal:4000/v1'],
    'api_keys': [{api_key!r}],
    'api_configs': {{
        '0': {{
            'enable': True,
            'tags': [],
            'prefix_id': '',
            'model_ids': {webui_aliases!r},
            'connection_type': 'external',
            'auth_type': 'bearer'
        }}
    }}
}}
data['ollama'] = {{
    'enable': False,
    'base_urls': [],
    'api_configs': {{}}
}}
payload = json.dumps(data, ensure_ascii=False)
now = time.strftime('%Y-%m-%d %H:%M:%S')
con.execute(
    'insert or replace into config (id, data, version, created_at, updated_at) values (?, ?, ?, coalesce((select created_at from config where id=?), ?), ?)',
    (config_id, payload, data.get('version', 0), config_id, now, now)
)
allowed = {sorted(allowed)!r}
if allowed:
    q = ','.join('?' for _ in allowed)
    con.execute(f'update model set is_active=0 where id not in ({{q}})', allowed)
con.commit()
print(json.dumps({{'openai_base_urls': data['openai']['api_base_urls'], 'allowed': allowed}}, ensure_ascii=False))
"""
    result = subprocess.run(
        ["docker", "exec", "-i", "open-webui", "python", "-c", code],
        check=True,
        text=True,
        capture_output=True,
    )
    config_payload = json.loads(result.stdout)
    print("openwebui=" + json.dumps(config_payload, ensure_ascii=False))


def compose_up(*services: str) -> None:
    subprocess.run(
        ["docker", "compose", "up", "-d", "--force-recreate", *services],
        cwd=OPENCLAW_DIR,
        check=True,
    )


def validate_litellm(env: dict[str, str]) -> list[str]:
    api_key = env.get("LITELLM_MASTER_KEY", "sk-openclaw-local")
    request = urllib.request.Request(
        "http://127.0.0.1:4000/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    last_error: Exception | None = None
    for _ in range(12):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return sorted(item["id"] for item in payload.get("data", []) if item.get("id"))
        except Exception as exc:
            last_error = exc
            time.sleep(5)
    raise RuntimeError(f"LiteLLM models endpoint not ready: {last_error}")


def main() -> None:
    env = parse_env(ENV_FILE)
    upstream = fetch_models()
    chat_models = [model_id for model_id in upstream if not is_embedding(model_id)]
    embedding_models = [model_id for model_id in upstream if is_embedding(model_id)]

    text_model = pick_model(chat_models, ("coder", "instruct", "qwen", "llama"))
    vision_model = pick_model(chat_models, ("vl", "vision", "multimodal"))
    embedding_model = pick_model(embedding_models, ("embed", "embedding"))

    if not text_model:
        raise SystemExit("No chat model available from " + MODELS_URL)

    selected = {
        "text": text_model,
        "vision": vision_model,
        "embedding": embedding_model,
    }

    aliases = write_litellm(env, text_model, vision_model, embedding_model)
    write_openclaw_config(aliases, selected)
    ROUTING_STATE.write_text(
        json.dumps(
            {
                "source": MODELS_URL,
                "available": upstream,
                "selected": selected,
                "aliases": aliases,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    compose_up("litellm", "openclaw-gateway", "openclaw-cli")
    sync_openwebui(env, aliases, chat_models)
    subprocess.run(["docker", "restart", "open-webui"], check=True)
    time.sleep(8)

    exposed = validate_litellm(env)
    missing = sorted(set(aliases) - set(exposed))
    if missing:
        raise SystemExit("LiteLLM missing aliases: " + ", ".join(missing))

    print(
        json.dumps(
            {
                "source": MODELS_URL,
                "selected": selected,
                "litellm_models": exposed,
                "cron": "installed when --install-cron is used",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
PY
