# Guía operativa — OpenClaw Mauro

## Clonar

```bash
git clone --recurse-submodules https://github.com/Maurog-castros/openclaw-ubuntu-server.git openclaw-mauro
cd openclaw-mauro
git submodule update --init --recursive
```

## Secretos y entorno

1. Revisa `secrets/README.md` y crea los archivos en `secrets/`.
2. Copia `config/stack.env.example` → `openclaw/.env` y completa tokens.
3. Genera config del gateway: `scripts/apply_openclaw_*.py` (crean `data/config/openclaw.json` local).

## Docker

```bash
docker build -t openclaw-with-ssh:local docker-overrides/openclaw-with-ssh
cd openclaw && docker compose up -d
```

## Actualizar OpenClaw upstream

```bash
cd openclaw && git pull origin main && cd ..
docker build -t openclaw-with-ssh:local docker-overrides/openclaw-with-ssh
cd openclaw && docker compose up -d --force-recreate
```

## Qué se versiona

| Sí (GitHub) | No (local) |
|-------------|------------|
| `scripts/`, `config/`, `docker-overrides/` | `secrets/` |
| Plugin `channel-delegate-hook` | `openclaw.json`, `.env` |
| Workspaces de agentes | Imágenes, boletas, auth WhatsApp |
| Submódulo `openclaw/` | `.venv-*`, `data/inbox/` |
