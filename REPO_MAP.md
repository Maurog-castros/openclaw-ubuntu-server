# Repository Map

> Estado: migracion fisica completada el 2026-06-20. Fase 2 (`runtime_paths`) en
> scripts versionados completada; enlaces de compatibilidad siguen activos.
> Consultar `REPO_REORGANIZATION_HANDOFF.md` para evidencias y fase 3 pendiente.

Este archivo es el punto de entrada para humanos y agentes. El checkout canonico
vive en `/home/mauro/Dev/openclaw-mauro` en Ubuntu. La unidad Windows `Y:` es una
vista por red; ejecucion, Git, permisos, cron y Docker se operan por SSH en Ubuntu.

## Reglas de ubicacion

- Codigo y documentacion durable: versionados en Git.
- Configuracion publicable: `config/`; secretos reales nunca entran a Git.
- Estado mutable: `runtime/`, ignorado por Git.
- Experimentos: `/tmp/openclaw-*`, fuera del repositorio.
- Repos externos: fuera de este checkout o como submodulo formal.
- Un archivo tiene una sola ubicacion canonica. Los enlaces solo existen durante
  migraciones y deben estar documentados aqui.

## Propiedad de carpetas

| Ruta | Propietario | Responsabilidad | Git |
|---|---|---|---|
| `.agents/` | Tooling de agentes | Skills y reglas compartidas por agentes | Si |
| `.cursor/` | Cursor | Adaptadores, skills y reglas de Cursor | Si |
| `config/` | Plataforma + agente de dominio | Configuracion declarativa y ejemplos sin secretos | Si |
| `content/` | Agente Content | Contenido editorial y borradores publicables | Selectivo |
| `crm/` | Agente Sales | Oportunidades comerciales curadas | Si |
| `data/` | Runtime legacy | Datos operativos antiguos durante la migracion | Selectivo |
| `docker-overrides/` | Plataforma | Overrides reproducibles de Docker | Si |
| `docs/` | Plataforma | Arquitectura, setup y operacion | Si |
| `graphify-out/` | Graphify | Indice y artefactos regenerables | No |
| `openclaw/` | Upstream OpenClaw | Submodulo formal; no mezclar codigo propio | Submodulo |
| `reports/` | Intel/Finanzas | Reportes curados; salida temporal va a runtime | Selectivo |
| `scripts/` | Plataforma + agentes | Entrypoints y automatizaciones durables | Si |
| `runtime/` | Servicio que escribe | Estado, secretos, logs y artefactos locales | No |

## Runtime canonico

| Ruta | Contenido | Permisos esperados |
|---|---|---|
| `runtime/jobs/cv-library/` | Biblioteca unica de CV para Jobs | `mauro:mauro`, directorio 750 |
| `runtime/secrets/` | OAuth, sesiones, tokens y credenciales | `mauro:mauro`, directorio 700 |
| `runtime/logs/` | Logs activos de cron y agentes | `mauro:mauro`, directorio 750 |

## Compatibilidad temporal

Estas rutas son **enlaces relativos** hacia `runtime/`. Los scripts versionados ya
resuelven rutas canonicas via `scripts/runtime_paths.py`; los enlaces permanecen
hasta que cron, Docker y docs agent-facing dejen de referenciarlos:

| Ruta legacy | Destino canonico | Consumidores |
|---|---|---|
| `content/CV` | `runtime/jobs/cv-library` | Docs agente Jobs, JSON historicos |
| `data/CV` | `runtime/jobs/cv-library` | Alias historico |
| `secrets` | `runtime/secrets` | Defaults CLI legacy (`resolve_repo_path`) |
| `data/secrets` | `runtime/secrets` | Alias historico |
| `logs` | `runtime/logs` | Crontab (`$ROOT/logs/*.log`) |

Helper canonico: `scripts/runtime_paths.py` — `cv_library_dir()`, `secrets_dir()`,
`logs_dir()`, `resolve_repo_path()`, `whatsapp_allow_files()`.

No eliminar estos enlaces hasta que `git grep`, `crontab -l` y la configuracion
Docker dejen de referenciar las rutas legacy (ver handoff fase 3).

## Rutas operativas principales

- Gateway config: `data/config/openclaw.json` (runtime, no versionado).
- Extension de routing: `data/config/extensions/channel-delegate-hook/`.
- Workspaces OpenClaw: `data/workspace/` (mezcla legacy en migracion).
- Jobs workspace: `data/workspace/jobs/`.
- Jobs config: `config/jobs/config.json`.
- Router de canales: `scripts/channel_delegate.py`.
- Submodulo OpenClaw: `openclaw/`.

## Politica de worktrees

- Checkout productivo: `/home/mauro/Dev/openclaw-mauro`.
- Trabajo paralelo: `/home/mauro/Dev/worktrees/openclaw-mauro/<rama>`.
- Nunca crear worktrees o clones dentro de `data/`, `runtime/` u `openclaw/`.
- La rama productiva se valida y confirma desde Ubuntu, no desde la unidad mapeada.

## Validacion minima

```bash
cd /home/mauro/Dev/openclaw-mauro
git status --short
find content/CV data/CV secrets data/secrets logs -maxdepth 0 -type l -ls
python3 -m py_compile scripts/jobs_common.py
.venv-linkedin-intel/bin/python scripts/jobs_cv_index.py --json
```
