# Agente `jobs` 📋

**Descripción:** Postulaciones laborales — match vacantes LinkedIn, CV y borradores.

## Qué hace

- **CV index** — `jobs_cv_index.py` (variantes DevOps, SRE, MLOps, Cloud…)
- **Búsqueda LinkedIn** — `jobs_linkedin_search.py` (URLs /jobs/view/)
- **Easy Apply** — `jobs_linkedin_apply.py` vía `jobs_apply.py`
- **Tracking** — `data/workspace/jobs/applications.csv` obligatorio
- **Informes** — `jobs_report.py` o resumen WhatsApp tras postular

## CVs

Directorio `content/CV/` — el match elige filename según tags del índice.

## Depende de

**intel** — señales LinkedIn (`linkedin_signals_*.json`). Refrescar con `/intel scan linkedin`.

## Workspace

`/home/node/.openclaw/workspace/jobs`  
Detalle: `jobs/AGENTS.md`
