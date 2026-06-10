# Agente boletas Lider (Gmail)

Este agente hace 2 cosas:

1. Lee Gmail y detecta boletas de Lider con PDF adjunto.
2. Extrae detalle y guarda filas en CSV para analisis mensual.

## 1) Instalar dependencias

```bash
python -m pip install -r scripts/requirements-lider-agent.txt
```

## 2) Configurar OAuth Gmail

1. En Google Cloud Console, habilita Gmail API.
2. Crea credenciales OAuth Desktop App.
3. Descarga el JSON y guardalo en:

```text
secrets/gmail_credentials.json
```

La primera vez que ejecutes el agente abrira login en navegador y creara:

```text
secrets/gmail_token.json
```

## 3) Ejecutar agente (manual)

```bash
python scripts/lider_receipts_agent.py
```

Salida principal:

```text
data/lider_receipts.csv
```

## 4) Programar cada 30 minutos (Windows Task Scheduler)

Crear tarea con:

- Trigger: Every 30 minutes, indefinitely
- Action:
  - Program/script: ruta a `python.exe`
  - Add arguments: `scripts/lider_receipts_agent.py`
  - Start in: `C:\DEV\openclaw-mauro`

## 5) Generar informe mensual

```bash
python scripts/lider_monthly_report.py --month 2026-05 --output reports/lider_2026-05.md
```

El informe muestra:

- gasto total del mes
- gasto por categoria
- top productos por gasto
