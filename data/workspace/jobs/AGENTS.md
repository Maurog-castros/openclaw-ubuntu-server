# AGENTS.md — Jobs

## Workflow

1. Si no hay `cv_index.json` reciente → `jobs_cv_index.py`.
2. Vacantes reales → `jobs_linkedin_search.py` (URLs /jobs/view/).
3. Evaluar oferta estilo career-ops → `jobs_ops.py` (score A-F + tracker + reporte). No postula.
4. Postular → `jobs_linkedin_apply.py` via `jobs_apply.py` (Easy Apply + preguntas LLM), solo cuando Mauro lo pide.
5. CSV obligatorio: `data/workspace/jobs/applications.csv`.
6. Informe → `jobs_report.py` o mensaje WhatsApp tras evaluar/postular.

## Career Ops

- El agente filtra oportunidades; no debe spamear postulaciones.
- Recomienda `apply`, `monitor` o `skip` con nota A-F.
- Estados canonicos: `evaluated`, `applied`, `responded`, `interview`, `offer`, `rejected`, `discarded`, `skip`.
- Cada evaluacion debe guardar reporte en `data/workspace/jobs/reports/`.
- Human-in-the-loop: aplicar solo con `/jobs postular N` o instruccion equivalente.

## CVs

Directorio: `content/CV/` — variantes DevOps, SRE, MLOps, AI, TechLead, Data, Cloud.
El match elige filename segun tags del indice.

## LinkedIn

Usa senales del scout Intel (`linkedin_signals_*.json`). Filtra posts tipo vacante/hiring.
Para refrescar fuentes: pedir `/intel scan linkedin` antes de match.

## Estilo WhatsApp

Espanol chileno profesional. Bullets cortos. Indica CV recomendado siempre.
