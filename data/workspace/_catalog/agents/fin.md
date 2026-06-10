# Agente `fin` 💰

**Prefijo:** `/fin` (legacy: `/finanzas`)  
**Descripción:** Gastos personales, boletas, transferencias y reportes mensuales Chile.

## Qué hace

- **Saldo Santander** — ancla + movimientos banco − boletas sin match
- **Boletas** — fotos con visión Iamiko; lista productos y montos
- **Transferencias** — reporte con observaciones por movimiento
- **Reportes mensuales** — gastos por mes, merchant, cuadratura cartola
- **Gmail Watch** — alertas de correos bancarios/comercio
- **Instagram** — análisis de posts vía `content_instagram_whatsapp.py` (enrutado content)

## Delegate obligatorio

```sh
/home/node/openclaw-mauro/scripts/run-finanzas-py.sh \
  /home/node/openclaw-mauro/scripts/finanzas_delegate.py --text "<mensaje>" [--has-media] --json
```

Copiar `whatsapp_reply` literal. NUNCA inventar saldos.

## Datos clave

- CSV: `/home/node/openclaw-mauro/data/finanzas_movimientos.csv`
- Media inbound: `/home/node/openclaw-mauro/data/config/media/inbound/`
- Python: `/home/node/openclaw-mauro/.venv-finanzas-docker/bin/python`

## Workspace

`/home/node/.openclaw/workspace/marketing/finanzas`  
Detalle: `marketing/finanzas/AGENTS.md`
