---
name: lead-finder
description: "Califica leads desde reports de Intel agente. Aplica senales de compra DevOps/IA, matchea producto-dolor, prioriza pipeline. NO envia mensajes. Trigger: 'califica leads', 'busca prospectos', 'pipeline desde intel', 'que leads tenemos'."
---

# lead-finder — Calificador de leads desde Intel

Lee outputs del agente Intel y los convierte en pipeline rankeado.

## Procedimiento

### 1. Leer fuentes

```sh
INTEL=/home/node/.openclaw/workspace/marketing/intel
ls -t $INTEL/reports/*.md 2>/dev/null | head -5
cat $INTEL/leads/leads.md 2>/dev/null
```

### 2. Aplicar senales de compra

**Alta prioridad:**
- Vacancy SRE/DevOps/Platform abierta < 14 dias
- Dolor publico DORA/observabilidad/costos cloud
- Migracion anunciada (Jenkins->GHA, monolito->K8s, on-prem->cloud)
- Incidente publico reciente
- Quejas explicitas medibles

**Media:**
- Crecimiento headcount tech rapido (Series A/B reciente)
- Adopcion herramienta nueva sin staff
- Vacante repetida >30 dias

**Ignorar:**
- Empresas <10 personas
- "Interes IA generica"
- Vacantes junior

### 3. Match producto-dolor

| Dolor detectado | Producto sugerido |
|---|---|
| Vacancy SRE/DevOps + sin tiempo de hire | Auditoria DevOps Express |
| Quejas DORA / no miden entrega | Auditoria + Consultoria |
| Documentacion mala / onboarding lento | Agente RAG Corporativo |
| MTTR alto / on-call saturado | Agente Observabilidad |
| Pipelines lentos/inseguros | Agente Auditor Pipelines + Consultoria |
| Costos cloud sin control | Consultoria FinOps |
| "Queremos IA pero no sabemos donde" | Auditoria + Pilot agente |

### 4. Output

Tabla markdown rankeada:

```
| Empresa | Persona | Stage propuesto | Senal | Producto | Ticket estimado | Prioridad | Proxima accion |
|---|---|---|---|---|---|---|---|
```

Y resumen:
- Top 3 leads alta prioridad
- Productos mas demandados esta semana
- Vacios / oportunidades nuevas

## Argumentos opcionales

- `since=<N>d` — ventana lookback Intel reports (default 7d)
- `min_priority=Alta|Media` — filtro
- `producto=<slug>` — solo leads matched a producto especifico

## Reglas

- NO inventar leads. Si Intel no detecto, decirlo.
- NO contactar / no enviar mensajes.
- Output a `leads/active.md` solo si agente Hook lo agrega explicito.
- Si lead duplicado (ya en active.md): no crear, agregar nota "ya en pipeline".
