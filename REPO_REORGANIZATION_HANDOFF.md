# Repository Reorganization Handoff

## Objetivo

Ordenar el checkout `/home/mauro/Dev/openclaw-mauro` sin interrumpir OpenClaw,
Jobs, OAuth, cron ni Docker. La unidad Windows `Y:` es solo una vista de red. Las
operaciones de filesystem, permisos, Git y validacion se ejecutan en Ubuntu:

```bash
ssh mauro@192.168.1.12
cd /home/mauro/Dev/openclaw-mauro
```

## Estado del checkpoint

Completado (2026-06-20, shell Ubuntu `/home/mauro/Dev/openclaw-mauro`):

- `REPO_MAP.md` creado y marcado como migrado.
- `README.md` enlaza al mapa.
- `.gitignore` ignora `runtime/` y enlaces legacy (`secrets`, `data/secrets`,
  `content/CV`, `data/CV`, `logs`).
- `docs/SECRETS.md` reemplaza la documentacion que estaba dentro de `secrets/`.
- `AGENTS.md` obliga a leer este handoff.
- CV unificados en `runtime/jobs/cv-library/` (45 archivos; 20 PDF indexables).
- Secretos unificados en `runtime/secrets/` (21 archivos; permisos 700/600).
- Logs activos en `runtime/logs/` (18 archivos).
- Backups movidos a `/home/mauro/backups/openclaw-mauro/` (permiso 700).
- Directorios vacios eliminados: `agents`, `.codex`, `configs`, `memory`,
  `prompts`, `backups`.
- Enlaces relativos creados (ver seccion Enlaces esperados).
- Conflictos CV resueltos segun SHA-256 (2 legacy `__legacy-content-CV-*`).
- Conflictos OAuth resueltos (`gmail_modify_*` activo desde `data/secrets`).
- Cron sin cambios (`crontab diff` exit 0).
- Commits de cierre: `9babfa7` (reorg docs), `7ea7659` (`pypdf` en linkedin-intel).
- `pypdf` instalado en `.venv-linkedin-intel`; shebangs corregidos a
  `/home/mauro/Dev/openclaw-mauro`.
- Shebangs corregidos en `.venv-finanzas` y `.venv-lider` (cron activo).

Pendiente fuera de alcance de esta fase:

- Retirar enlaces legacy cuando `git grep`, crontab y Docker dejen de usarlos
  (fase 3; ver audit refs legacy y seccion Fase 2).
- Actualizar textos agent-facing en `apply_openclaw_*_config.py` y skills
  (`content/CV`, `secrets/` en markdown) — symlinks siguen cubriendo.

Resuelto post-fase-1:

- `openclaw` en PATH via `bin/openclaw` → gateway Docker; delegates usan
  `scripts/openclaw_cli.py` (`OPENCLAW_BIN` / `OPENCLAW_GATEWAY_CONTAINER` opcionales).

## Reglas canonicas de esta fase

| Contenido | Destino canonico | Enlaces temporales |
|---|---|---|
| Biblioteca de CV | `runtime/jobs/cv-library/` | `content/CV`, `data/CV` |
| Secretos | `runtime/secrets/` | `secrets`, `data/secrets` |
| Logs activos | `runtime/logs/` | `logs` |
| Backups antiguos | `/home/mauro/backups/openclaw-mauro/` | Ninguno |

No mover en esta fase: `data/workspace`, `data/config`, `openclaw`, `.venv-*`,
`graphify-out`, `scripts`, `config`, `content` restante ni repos anidados.

## Preflight obligatorio

```bash
cd /home/mauro/Dev/openclaw-mauro
git status --short
crontab -l > /tmp/openclaw-crontab-before-reorg.txt
find content/CV data/CV secrets data/secrets logs backups \
  -maxdepth 1 -printf '%y %m %u:%g %p\n'
```

El arbol ya estaba sucio antes de esta tarea. No revertir cambios de otros
agentes. Trabajar solo sobre los archivos descritos en este handoff.

## Migracion segura

1. Crear `runtime/jobs/cv-library`, `runtime/secrets` y `runtime/logs`.
2. Verificar con `realpath -m` que todos los origenes estan bajo el checkout y
   que el backup externo esta bajo `/home/mauro/backups/openclaw-mauro/`.
3. Fusionar CV por SHA-256. Eliminar solo copias byte-a-byte identicas.
4. Para mismo nombre con hash diferente, conservar ambas y agregar a la version
   secundaria `__legacy-<origen>-<hash8>` antes de la extension.
5. Fusionar secretos sin imprimir contenido, tokens, passwords ni client secret.
6. Crear enlaces relativos solo despues de comprobar el destino.
7. Mover logs activos y dejar `logs -> runtime/logs`, porque cron aun usa `logs/`.
8. Mover `backups/` fuera del repo con permisos `700`; contiene un `.env` real.
9. Eliminar solo directorios de raiz confirmados vacios.

Directorios vacios detectados:

```text
agents
.codex
configs
memory
prompts
```

## Conflictos de CV conocidos

Estos nombres tienen contenido diferente en ambos origenes. La copia de
`data/CV` es mas reciente y debe conservar el nombre original; la copia de
`content/CV` debe preservarse como legacy:

```text
CV_Mauricio_Castro_DevOps__Falabella.docx
CV_Mauricio_Castro_TechLead_Node_React_PostgreSQL.docx
```

Hay otros CV identicos por SHA-256 con nombres diferentes. Deduplicarlos solo si
el indice o los reportes no necesitan el alias; en caso contrario mantener un
symlink con el nombre historico.

## Conflictos de secretos conocidos

- `data/secrets/gmail_modify_token.json` incluye `gmail.modify` y
  `gmail.readonly`; debe quedar activo con el nombre original.
- `secrets/gmail_modify_token.json` solo incluye `gmail.readonly`; preservarlo
  como legacy, no dejarlo activo para operaciones modify.
- `gmail_modify_oauth_pending.json` difiere; la copia de `data/secrets` es mas
  reciente. Preservar la otra con sufijo legacy.
- Aplicar `chmod 700 runtime/secrets` y `chmod 600 runtime/secrets/*`.

## Enlaces esperados

Todos deben ser relativos:

```text
content/CV  -> ../runtime/jobs/cv-library
data/CV     -> ../runtime/jobs/cv-library
secrets     -> runtime/secrets
data/secrets -> ../runtime/secrets
logs        -> runtime/logs
```

`config/jobs/config.json` debe seguir con `cv_dir: content/CV` durante esta fase.
El enlace mantiene compatibilidad con JSON y reportes que contienen rutas
historicas.

## Validacion obligatoria

```bash
cd /home/mauro/Dev/openclaw-mauro
find content/CV data/CV secrets data/secrets logs -maxdepth 0 -type l -ls
test -r content/CV/CV_MauricioCastro-IaC-022026.pdf
test -r secrets/linkedin_storage_state.json
test -r data/secrets/.env
python3 -m py_compile scripts/jobs_common.py scripts/jobs_cv_index.py
.venv-linkedin-intel/bin/python scripts/jobs_cv_index.py --json
.venv-linkedin-intel/bin/python scripts/test_jobs_profile.py
python3 scripts/channel_delegate.py --text '/jobs ayuda' \
  --peer +56945046845 --json
crontab -l | diff -u /tmp/openclaw-crontab-before-reorg.txt -
git status --short
```

### Resultados 2026-06-20

| Check | Resultado |
|---|---|
| Symlinks | 5 enlaces relativos OK (`find … -type l`) |
| CV legible via `content/CV` | OK |
| OAuth via `secrets/` y `data/secrets/` | OK |
| `py_compile` jobs | OK |
| `jobs_cv_index.py` (handoff venv) | OK — 20 PDF (`7ea7659` + shebang fix) |
| `test_jobs_profile.py` | OK (4 tests) |
| `channel_delegate /jobs ayuda` | OK — `openclaw_cli.py` + gateway Docker |
| Crontab sin cambios | OK (`diff` exit 0) |
| Permisos runtime | `750` cv-library/logs, `700` secrets, archivos `600` |
| Gmail modify activo | OK — scope `gmail.modify` en token activo; legacy solo `readonly` |
| Backups fuera del repo | OK — `/home/mauro/backups/openclaw-mauro/openclaw-update-20260601-001303/` |

Evidencia symlinks:

```text
content/CV -> ../runtime/jobs/cv-library
data/CV -> ../runtime/jobs/cv-library
secrets -> runtime/secrets
data/secrets -> ../runtime/secrets
logs -> runtime/logs
```

CV legacy por conflicto SHA-256:

```text
CV_Mauricio_Castro_DevOps__Falabella__legacy-content-CV-378b62e7.docx
CV_Mauricio_Castro_TechLead_Node_React_PostgreSQL__legacy-content-CV-2eb451dc.docx
```

Secretos legacy:

```text
gmail_modify_token__legacy-secrets-d638bd83.json
gmail_modify_oauth_pending__legacy-secrets-a8d045f0.json
```

No reiniciar contenedores para esta fase. Si Jobs u OAuth no pueden leer una
ruta, restaurar el directorio desde el destino canonico y revisar el enlace; no
regenerar credenciales ni iniciar login nuevo.

## Cierre esperado

- [x] Actualizar este archivo con fecha, resultado y comandos de validacion.
- [x] Marcar `REPO_MAP.md` como migrado.
- [x] Ejecutar `git status --short`.
- [x] Confirmar solo documentacion y reglas versionadas; `runtime/` queda fuera de
  Git y nunca debe incluirse en un commit.

Commits: `9babfa7`, `7ea7659`. Graphify refresh post-reorg OK (200k nodos;
`graph.html` omitido por limite de viz).

## Audit refs legacy (2026-06-20)

Inventario antes de retirar symlinks. Conteos en `scripts/` + `config/` versionados
(excluye `data/workspace/`, docs de reorg y submodulo `openclaw/` upstream):

| Patron legacy | Archivos | Notas |
|---|---|---|
| `content/CV` | 7 | Jobs config + `jobs_common.py` default |
| `data/CV` | 1 | `jobs_laborum_profile.py` (sin track aun) |
| `secrets/` | ~39 | Finanzas, Jobs portales, HL-Go, Intel, WhatsApp |
| `data/secrets` | 9 | OAuth pending/tokens, `.env` portales, `google_workspace_oauth.py` |
| `logs/` | 11 | Cron shell scripts + `graphify_repo_refresh.sh` |

### Cron (activo)

Todas las entradas OpenClaw escriben a `$ROOT/logs/*.log` (7 lineas). El symlink
`logs -> runtime/logs` las satisface; migrar implica editar crontab o wrappers.

Sin refs a `content/CV`, `secrets/` ni `data/secrets` en crontab.

### Docker / stack

Sin refs legacy en `docker-overrides/`. Mounts de secretos/logs viven en
`openclaw/docker-compose*.yml` (revisar en fase 2 con stack productivo).

### Prioridad de migracion sugerida

1. **Helper unico** — `runtime_paths.py` con `cv_dir()`, `secrets_dir()`, `logs_dir()`
   (similar a `openclaw_cli.py`); reemplazar defaults hardcodeados.
2. **Jobs** — `config/jobs/config.json`, `jobs_common.py`, browsers Laborum/ChileTrabajos.
3. **OAuth / finanzas** — `vida_common.py`, gmail agents, `google_workspace_oauth.py`.
4. **Cron scripts** — `$ROOT/logs/` → `$ROOT/runtime/logs/` o env `OPENCLAW_LOG_DIR`.
5. **Agent docs** — SOUL.md / skills (baja prioridad; symlinks cubren).
6. **Retirar symlinks** — solo cuando conteos lleguen a 0 en scripts+cron+Docker.

### Fuera de alcance del audit

- `data/workspace/jobs/**` — rutas embebidas en JSON de vacantes (runtime).
- `REPO_MAP.md`, `REPO_REORGANIZATION_HANDOFF.md`, `docs/SECRETS.md` — documentacion.
- `openclaw/` submodulo — `src/secrets/` es codigo upstream, no repo local.

## Fase 2 — runtime_paths (2026-06-20)

Completado:

- `scripts/runtime_paths.py` + `scripts/test_runtime_paths.py` (6 tests OK).
- Jobs: `config/jobs/config.json`, `jobs_common.py`, browsers, `jobs_laborum_*`,
  `jobs_profile*.py`, `jobs_profile_init.py`, `profiles.json`, `_template.json`.
- Secretos/OAuth: `vida_common.py`, `google_workspace_oauth.py`, `gmail_modify_oauth.py`,
  `vida_calendar_oauth.py`, `jobs_laborum_mfa_gmail.py`, `hl_go_common.py`,
  `config/linkedin_intel/config.json`.
- Logs cron: scripts `*.sh` migrados a `$ROOT/runtime/logs/` (symlink sigue OK).
- Finanzas Gmail CLI: `gmail_watch_agent.py`, `gmail_organize_agent.py`,
  `transferencias_agent.py`, `santander_cartola_agent.py`, `lider_receipts_agent.py`
  (defaults legacy + `resolve_repo_path` al leer).
- WhatsApp allow: `setup_whatsapp_openclaw.sh`, `apply_openclaw_finanzas_config.py`,
  `channel_user_context.py`, `jobs_daily_auto.py`, `intel_chile_daily_report.py`.
- `linkedin_intel_scout.py`, `deploy_vida.py` (plantillas calendar OAuth).
- `jobs_chiletrabajos_scrape.py` default storage_state → `runtime/secrets/`.

Pendiente fase 3 (retirar symlinks):

- Textos en agent docs/skills (`apply_openclaw_*_config.py`, `config/jobs/*.md`) —
  baja prioridad; symlinks cubren.
- Argparse defaults que aún dicen `secrets/...` (compat CLI; resuelven vía
  `resolve_repo_path`).
- Crontab: entradas escriben a `$ROOT/logs/*.log` (7 lineas); symlink activo.
- Docker: mounts en `openclaw/docker-compose*.yml` (revisar con stack productivo).
- Retirar symlinks cuando refs legacy en scripts+cron+Docker = 0.

Validacion fase 2b (2026-06-20):

```bash
cd /home/mauro/Dev/openclaw-mauro
python3 -m py_compile scripts/runtime_paths.py scripts/gmail_watch_agent.py \
  scripts/gmail_organize_agent.py scripts/transferencias_agent.py \
  scripts/setup_whatsapp_openclaw.sh 2>/dev/null || true
python3 scripts/test_runtime_paths.py
.venv-linkedin-intel/bin/python scripts/test_jobs_profile.py
python3 scripts/channel_delegate.py --text '/jobs ayuda' --peer +56945046845 --json
find content/CV data/CV secrets data/secrets logs -maxdepth 0 -type l -ls
```
