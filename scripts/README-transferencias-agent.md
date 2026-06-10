# Job Gmail: transferencias Santander

Igual que el job de boletas Líder, este script revisa Gmail y registra **salidas de dinero** desde comprobantes:

- **De:** `mensajeria@santander.cl`
- **Asunto:** `Comprobante Transferencia de fondos`

Salida: `data/transferencias.csv` → merge en `data/finanzas_movimientos.csv` como `transferencia_salida` (o entrada si el destino es tu RUT).

## Requisitos

Misma OAuth Gmail que Líder:

- `secrets/gmail_credentials.json`
- `secrets/gmail_token.json` (se crea en el primer login)

```bash
pip install -r scripts/requirements-lider-agent.txt
```

## Ejecutar manual

```bash
python scripts/transferencias_agent.py
python scripts/transferencias_agent.py --json
```

Probar parser con un correo guardado:

```bash
python scripts/transferencias_agent.py --parse-eml "sample-transferencias/Comprobante Transferencia de fondos.eml"
```

## Job automático (cada 30 min)

Ya está en el pipeline:

```bash
bash scripts/run_finanzas_pipeline.sh
```

Cron en servidor (ejemplo):

```cron
*/30 * * * * cd /home/mauro/openclaw-mauro && .venv-finanzas/bin/python scripts/transferencias_agent.py && .venv-finanzas/bin/python scripts/finanzas_merge.py >> logs/finanzas-pipeline.log 2>&1
```

## Campos en CSV

| Columna | Ejemplo |
|---------|---------|
| `transfer_date` | 2026-06-02 |
| `amount_clp` | 2000 |
| `destination_name` | Mauricio Guillermo Castro Sandoval |
| `destination_bank` | Banco Crédito e Inversiones |
| `destination_account_number` | 7-779-15-89415-0 |
| `comment` | (opcional, desde origen) |

## Clasificación en finanzas

Con `FINANZAS_OWNER_RUT=15.894.150-3` (opcional, mejora descripciones):

- Todos los comprobantes Gmail son **`transferencia_salida`** (dinero que sale de tu Santander), incluso si el destino es otra cuenta tuya (ej. BCI para pagos).
- Mismo RUT en destino → descripción `Transferencia a cuenta propia (Banco …)`

```bash
python scripts/finanzas_merge.py --owner-rut 15.894.150-3
```

## Estado / dedup

- `data/transferencias_state.json` — IDs Gmail ya procesados
- Huella `fecha|monto|rut destino|cuenta` evita duplicar el mismo comprobante
