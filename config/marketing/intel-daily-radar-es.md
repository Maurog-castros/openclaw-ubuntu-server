<!-- DAILY_RADAR_ES -->

## Daily Radar WhatsApp — siempre en espanol

El radar diario (cron `run-intel-daily-radar-whatsapp.sh`, `/intel daily`, consolidado) debe leerse **100% en espanol chileno tecnico**.

### Reglas obligatorias

1. **Cada item de fuente** (HN, Reddit, GitHub, LinkedIn): titulo **resumido y compacto** (max ~72 caracteres). Si la fuente esta en ingles u otro idioma, **traducir a espanol** antes de mostrar.
2. **Conservar** nombres propios y marcas (Kubernetes, Langfuse, Microsoft, DevOpsDays).
3. **Secciones del mensaje** siempre en espanol: Tendencias Fuertes, Dolores Reales, Prospectos, Ideas de Contenido, Ideas de Producto, Fuentes usadas.
4. **Metricas** en espanol: `puntos HN`, `comentarios` (no "score"/"comments").
5. **Pipeline deterministico**: `scripts/intel_daily_report.py` + `intel_localize.py` localizan titulos; el agente LLM debe seguir las mismas reglas si resume manualmente.

### Formato sintesis final (WhatsApp)

```
🧭 Intel Daily - Sintesis final — YYYY-MM-DD
🔥 Tendencias Fuertes
🎯 Dolores Reales (Oportunidades)
📊 Prospectos Detectados
💡 Ideas de Contenido
💰 Ideas de Producto
📡 Fuentes usadas
```

Prohibido dejar titulos crudos en ingles en bullets o listas numeradas del daily.
