# openclaw-ubuntu-server

Stack personal de **OpenClaw** en Ubuntu/DMZ: WhatsApp, Telegram, agentes finanzas, care, HL-Go, intel, jobs y content.

Repositorio: [github.com/Maurog-castros/openclaw-ubuntu-server](https://github.com/Maurog-castros/openclaw-ubuntu-server)

## Qué se versiona y qué no

| Sí (GitHub) | No (local / ignorado) |
|-------------|------------------------|
| `scripts/`, `config/`, `docker-overrides/` | `secrets/` |
| Plugin `data/config/extensions/channel-delegate-hook/` | `data/config/openclaw.json` (tokens) |
| Workspaces de agentes (`data/workspace/**` excepto `memory/`) | Imágenes (`*.jpg`, `*.png`, boletas, CV) |
| `.cursor/`, `content/` (texto), `projects/` | `.venv-*`, `data/inbox/`, auth WhatsApp |
| Submódulo `openclaw/` (upstream) | `openclaw/.env` |

## Clonar

```bash
git clone --recurse-submodules https://github.com/Maurog-castros/openclaw-ubuntu-server.git openclaw-mauro
cd openclaw-mauro
```

Si ya clonaste sin submódulos:

```bash
git submodule update --init --recursive
```

## Secretos y entorno

1. Revisa `secrets/README.md` y crea los archivos en `secrets/`.
2. Copia `config/stack.env.example` → `openclaw/.env` y completa tokens.
3. Genera config del gateway con los scripts `apply_openclaw_*.py` (crean `data/config/openclaw.json` local).

## Docker

```bash
# Imagen con SSH/git/gh (ajusta versión en docker-overrides/openclaw-with-ssh/Dockerfile)
docker build -t openclaw-with-ssh:local docker-overrides/openclaw-with-ssh

cd openclaw
docker compose up -d
```

## Primer push (desde esta máquina)

```bash
git remote add origin https://github.com/Maurog-castros/openclaw-ubuntu-server.git   # si no existe
git add -A
git status   # verificar que no hay secretos ni imágenes
git commit -m "chore: configuración inicial del stack OpenClaw Mauro"
git push -u origin main
```

## Actualizar OpenClaw upstream

```bash
cd openclaw && git pull origin main && cd ..
# Rebuild imagen si cambió la versión base en Dockerfile
docker build -t openclaw-with-ssh:local docker-overrides/openclaw-with-ssh
cd openclaw && docker compose up -d --force-recreate
```
