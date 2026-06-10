# TOOLS.md

## Rutas
- Repos: `/home/node/repos`
- Config host: `/home/mauro/openclaw-mauro`
- Workspace: `/home/node/.openclaw/workspace`

## Comandos utiles
```sh
host-sh "docker ps -a"
host-sh "/home/mauro/openclaw-mauro/data/config/bin/host-status-telegram"
repo-gitlog 15
rg "texto"
gh auth status
```

## LLM
OpenClaw usa LiteLLM:

```text
http://litellm:4000/v1
```

Ollama host:

```text
http://host.docker.internal:11434
```

## OpenAI API
La API key OpenAI esta guardada en `/home/mauro/openclaw-mauro/openclaw/.env` como `OPENAI_API_KEY`.
No imprimir ni reenviar la key.
Default LiteLLM:

```text
openclaw-auto -> openai/gpt-4.1-mini -> fallback openclaw-local-fast
```

## Exec preflight OpenClaw 2026.5.31
Permitido:
```sh
python3 /home/node/.openclaw/workspace/analyze_lider.py
```
Evitar para Python:
```sh
cd /home/node/.openclaw/workspace && python3 analyze_lider.py
python3 -c "..."
python3 - <<'PY'
```
