---
product: agente-observabilidad
ticket_usd: 3000-12000
duracion: 4-6 semanas
---

# Agente IA de Observabilidad

## Para quien

- Equipos con metrics/logs/traces pero sin correlacion automatica
- On-call saturado de pages, MTTR alto
- Stack Datadog/Grafana/NewRelic/ELK ya invertido pero subutilizado

## Que hace

- Triage automatico alertas (severity + causa probable)
- Resumen incidente con contexto (RCA preliminar)
- Sugerencia de runbook segun patron
- Postmortem skeleton tras incidente

## Stack tipico

- Ingest: APIs observabilidad existente
- LLM: Gemini Flash o GPT-5 Mini (latencia critica)
- Vector: historico incidentes
- UI: Slack bot integrado al canal de alertas

## Pricing

- Pilot 1 servicio: USD $3.000
- Standard multi-servicio: USD $7.000
- Enterprise: USD $10.000-$12.000

## Como cerrarla

- Senal: incident publico + queja MTTR + uso Datadog/Grafana mencionado
- Demo en vivo con un alerta sintetica = killer
