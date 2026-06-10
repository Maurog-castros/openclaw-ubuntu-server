---
name: jobs-postula
description: >-
  Agente Jobs para postular: matchea vacantes LinkedIn con el perfil de Mauro,
  postula automaticamente en LinkedIn Easy Apply, responde preguntas del formulario,
  registra CSV con fecha/hora/URL e informa al usuario. Usar con /jobs, /postula,
  vacantes devops, postular auto o mis postulaciones.
---

# Jobs — postulaciones laborales

Agente exclusivo **jobs** (`/jobs`, `/postula`). Espanol chileno profesional.

## Arquitectura

| Pieza | Ruta |
|-------|------|
| Delegate | `scripts/jobs_delegate.py` |
| Index CV | `scripts/jobs_cv_index.py` |
| Buscar LinkedIn Jobs | `scripts/jobs_linkedin_search.py` |
| Postular Easy Apply | `scripts/jobs_linkedin_apply.py` |
| Orquestador postular | `scripts/jobs_apply.py` |
| Informe CSV | `scripts/jobs_report.py` |
| CSV | `data/workspace/jobs/applications.csv` |
| CVs | `content/CV/` |
| Sesion LI personal | `secrets/linkedin_storage_state.json` |

## Flujo WhatsApp

1. `/jobs indexar cv`
2. `/jobs buscar linkedin` — vacantes con URL `/jobs/view/`
3. `/jobs postular 1` o `postular auto` (max 3)
4. `/jobs mis postulaciones` — historial CSV

## Login LinkedIn (una vez)

```bash
.venv-linkedin-intel/bin/python scripts/jobs_linkedin_login.py login --headed
```

## Cron diario (09:00)

```bash
bash scripts/install-jobs-cron.sh
# Manual:
bash scripts/run-jobs-daily-auto-whatsapp.sh
```

Busca vacantes LinkedIn, postula hasta 3 (Easy Apply), registra CSV y avisa por WhatsApp.

## Registrar agente

```bash
python3 scripts/apply_openclaw_jobs_config.py
```
