# Agente `intel`

**Prefijo:** `/intel`  
**Descripción:** Radar de tendencias DevOps, leads comerciales, análisis YouTube.

## Qué hace

- **Daily radar** — Hacker News, Reddit, GitHub Trending → `reports/YYYY-MM-DD-daily.md`
- **Leads** — prospectos en `leads/leads.md` desde señales de compra
- **YouTube** — resumen y debate de videos técnicos (`intel_youtube.py`)
- **LinkedIn signals** — señales de vacantes/hiring para Jobs y Sales
- Filtros: DevOps enterprise, observabilidad, DORA, FinOps, MLOps (no crypto/hype)

## Comandos típicos

- `/intel daily` — reporte del día
- `/intel scan linkedin` — refrescar señales LinkedIn
- `node fetch_trends.js` desde el workspace intel

## Workspace

`/home/node/.openclaw/workspace/marketing/intel`  
Detalle: `marketing/intel/AGENTS.md`

## Alimenta a

- **content** — borradores desde reports
- **sales** — leads calificados
- **jobs** — vacantes LinkedIn
