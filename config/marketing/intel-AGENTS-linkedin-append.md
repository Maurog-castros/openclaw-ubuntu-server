## LinkedIn — Innovación Radical (solo lectura)

Cuenta empresa: [Innovación Radical](https://www.linkedin.com/company/innovaci%C3%B3nradical/) · innovacionradical.cl

### Cuándo usar

Si Mauro pide **LinkedIn**, **tendencias LinkedIn**, **posts competidores**, **borrador LinkedIn** o **scan linkedin**:

1. Ejecutar:
   `python3 /home/node/openclaw-mauro/scripts/linkedin_intel_scout.py scan --json`
   (En host: `/home/mauro/openclaw-mauro/.venv-linkedin-intel/bin/python ...`)
2. Leer el JSON: `signals`, `report_path`, `draft_path`.
3. Resumir top 5 señales con autor + URL.
4. Mencionar borradores en `content/drafts/linkedin/` — **publicación manual**, nunca auto-post.

### Login / sesión

Si `scan` falla por sesión: avisar a Mauro. Login una vez:
`linkedin_intel_scout.py login --headed` (ver README-linkedin-intel.md).

### Keywords monitoreadas

devops, sre, agentes ia, mlops, machine learning, llms, rag, observabilidad, finops, kubernetes.

Competidores: `config/linkedin_intel/config.json` → array `competitors`.

### Integración daily

Opcional: tras `fetch_trends.js`, si existe reporte LinkedIn del día, incluir sección «LinkedIn» en el daily.

### Prohibido

- Publicar, comentar o dar like automáticamente.
- Mezclar con cuenta personal de jobs (`secrets/linkedin_storage_state.json`).
