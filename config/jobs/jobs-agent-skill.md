# AGENTS.md — Jobs

## Workflow

1. Si no hay `cv_index.json` reciente → `jobs_cv_index.py`.
2. Vacantes reales → `jobs_linkedin_search.py` (URLs /jobs/view/).
3. Postular → `jobs_linkedin_apply.py` via `jobs_apply.py` (Easy Apply + preguntas LLM).
4. CSV obligatorio: `data/workspace/jobs/applications.csv`.
5. Informe → `jobs_report.py` o mensaje WhatsApp tras postular.

## CVs

Directorio: `content/CV/` — variantes DevOps, SRE, MLOps, AI, TechLead, Data, Cloud.
El match elige filename segun tags del indice.

## LinkedIn

Usa senales del scout Intel (`linkedin_signals_*.json`). Filtra posts tipo vacante/hiring.
Para refrescar fuentes: pedir `/intel scan linkedin` antes de match.

## Estilo WhatsApp

Espanol chileno profesional. Bullets cortos. Indica CV recomendado siempre.
