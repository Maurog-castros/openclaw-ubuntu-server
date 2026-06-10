# Agente finanzas unificado (boletas + transferencias)

Pipeline hibrido:

- **Gmail Lider** → `data/lider_receipts.csv`
- **Gmail Santander** → `data/transferencias.csv`
- **Fotos boleta** (Telegram / web / manual) → `data/receipts_vision.csv` via **`qwen3-vl-30b-a3b-instruct`**
- **CSV maestro** → `data/finanzas_movimientos.csv`

Modelos Iamiko: [ia.iamiko.cl/v1/models](https://ia.iamiko.cl/v1/models)

| Modelo | Rol |
|--------|-----|
| `qwen3-vl-30b-a3b-instruct` | OCR boletas en foto |
| `qwen3.5-35b-a3b-abliterated` | Chat analisis finanzas (texto) |
| Alias LiteLLM `openclaw-remote-vision` | Vision dentro de OpenClaw |

---

## 1) Instalar dependencias

```powershell
cd C:\DEV\openclaw-mauro
python -m pip install -r scripts/requirements-finanzas-agent.txt
python -m pip install -r scripts/requirements-lider-agent.txt
```

Variables de entorno (`.env` o sistema):

```env
OPENCLAW_PRIMARY_URL=https://ia.iamiko.cl/v1
LITELLM_MASTER_KEY=sk-openclaw-local
OPENCLAW_VISION_MODEL=qwen3-vl-30b-a3b-instruct
FINANZAS_OWNER_RUT=12.345.678-9
```

`FINANZAS_OWNER_RUT` clasifica transferencias Santander como entrada vs salida.

---

## 2) Esquema CSV unificado

Archivo: `data/finanzas_movimientos.csv`

| Columna | Descripcion |
|---------|-------------|
| `movement_id` | Hash deduplicacion |
| `movement_type` | `gasto` \| `transferencia_salida` \| `transferencia_entrada` |
| `source` | `lider_gmail` \| `telegram_foto` \| `openclaw_web` \| `manual` \| `santander_gmail` |
| `movement_date` / `movement_datetime` | Fecha movimiento |
| `merchant` | Comercio (Simi, Lider, Santander...) |
| `merchant_rut` | RUT comercio si aplica |
| `document_number` | Numero boleta |
| `description` | Producto o comentario transferencia |
| `category` | Categoria (farmacia, despensa, transferencias...) |
| `amount_clp` | Monto linea |
| `ticket_total` | Total documento |
| `counterparty` | Contraparte en transferencias |

Regenerar manualmente:

```powershell
python scripts/finanzas_merge.py
python scripts/finanzas_merge.py --owner-rut 12.345.678-9 --json
```

---

## Dedup boletas

Antes de ingresar al CSV:

1. **Hash imagen** (SHA256) — misma foto exacta → skip sin OCR
2. **Fingerprint boleta** — tras OCR: `nº boleta + fecha + total` (o comercio+fecha+total si no hay nº)
3. **Registry** — `data/receipts_registry.json` persiste boletas vistas
4. **Merge cross-fuente** — Lider Gmail gana sobre foto Telegram si misma boleta

Respuesta skip: `duplicate_image` | `duplicate_receipt` (incluye `existing` con registro previo).

Una imagen:

```powershell
python scripts/receipt_vision_agent.py --image "ruta\boleta.jpg" --source manual --merge
```

Carpeta inbox (Telegram u OpenClaw guardan ahi):

```powershell
python scripts/receipt_vision_agent.py --inbox data/inbox/boletas --merge --source telegram_foto
```

Salida intermedia: `data/receipts_vision.csv`  
Estado dedup: `data/receipts_vision_state.json`  
Procesadas movidas a: `data/inbox/boletas/processed/`

---

## 4) Pipeline completo (Task Scheduler)

Script PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_finanzas_pipeline.ps1
```

Programar cada 30 min (igual que Lider):

- Program: `powershell.exe`
- Arguments: `-ExecutionPolicy Bypass -File C:\DEV\openclaw-mauro\scripts\run_finanzas_pipeline.ps1`
- Start in: `C:\DEV\openclaw-mauro`

En servidor Ubuntu (cron):

```bash
*/30 * * * * cd /home/mauro/openclaw-mauro && python scripts/lider_receipts_agent.py && python scripts/transferencias_agent.py && python scripts/receipt_vision_agent.py --inbox data/inbox/boletas --merge && python scripts/finanzas_merge.py >> logs/finanzas-pipeline.log 2>&1
```

---

## 5) Config OpenClaw — agente finanzas

Archivo servidor: `/home/mauro/openclaw-mauro/data/config/openclaw.json`

Ejemplo completo en: `config/finanzas/openclaw-finanzas.example.json`

### Agente finanzas

Agregar en `agents.list`:

```json
{
  "id": "finanzas",
  "name": "Finanzas",
  "workspace": "/home/mauro/openclaw-mauro",
  "model": {
    "primary": "remote-lm/openclaw-remote",
    "fallbacks": [
      "remote-lm/openclaw-remote-vision",
      "remote-lm/openclaw-remote-coder"
    ]
  }
}
```

- Chat normal → modelo texto (`qwen3.5-35b` o `qwen3-coder-next` via LiteLLM).
- Imagen → fallback `openclaw-remote-vision` = `qwen3-vl-30b-a3b-instruct`.

Verificar alias vision existe:

```bash
curl -s http://127.0.0.1:4000/v1/models -H "Authorization: Bearer sk-openclaw-local"
# Debe listar openclaw-remote-vision
```

Si falta, correr en servidor:

```bash
/home/mauro/openclaw-mauro/scripts/sync-openclaw-models.sh
```

### Vision model con input image

En `models.providers.remote-lm.models`, el entry `openclaw-remote-vision` debe incluir:

```json
"input": ["text", "image"]
```

(Si solo dice `["text"]`, OpenClaw no enruta fotos al modelo vision.)

---

## 6) Config OpenClaw — Telegram → finanzas

Problema actual: bot **clawcode-mauro** usa agente texto → fotos fallan.

### Opcion A — Enrutar fotos al agente finanzas (recomendado)

En `openclaw.json`, seccion `channels.telegram`:

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "botToken": "TU_BOT_TOKEN",
      "defaultAgent": "main",
      "agentByKind": {
        "photo": "finanzas",
        "document": "finanzas"
      },
      "mediaDownloadDir": "/home/mauro/openclaw-mauro/data/inbox/boletas"
    }
  }
}
```

Nombres exactos de campos pueden variar segun version OpenClaw. Si tu build usa `routing` en lugar de `agentByKind`, equivalente:

```json
"routing": {
  "photo": "finanzas",
  "document": "finanzas"
}
```

Reiniciar gateway:

```bash
cd /home/mauro/openclaw-mauro/openclaw
docker compose restart openclaw-gateway
```

### Opcion B — Hook post-descarga (sin depender del LLM vision en chat)

Cron cada 5 min procesa inbox:

```bash
python scripts/receipt_vision_agent.py --inbox data/inbox/boletas --merge --source telegram_foto
```

Telegram solo guarda foto en inbox; script hace OCR + CSV. Agente finanzas responde preguntas sobre `finanzas_movimientos.csv`.

### Opcion C — Segundo bot solo finanzas

Bot dedicado `@finanzas_mauro_bot` → `defaultAgent: "finanzas"`. Mas claro si quieres separar clawcode (dev) de finanzas.

---

## 6b) WhatsApp → finanzas (numero dedicado)

Documentacion: [docs.openclaw.ai/channels/whatsapp](https://docs.openclaw.ai/channels/whatsapp)

### Instalacion (una vez, en servidor)

Plugin oficial (si no esta en la imagen Docker):

```bash
docker compose -f /home/mauro/openclaw-mauro/openclaw/docker-compose.yml exec openclaw-cli \
  openclaw plugins install clawhub:@openclaw/whatsapp
```

Setup automatizado:

```bash
bash /home/mauro/openclaw-mauro/scripts/setup_whatsapp_openclaw.sh
```

Antes edita tu numero personal (quien escribe al bot):

```text
/home/mauro/openclaw-mauro/secrets/whatsapp_allow_from.txt
+569XXXXXXXX
```

O variable:

```bash
export FINANZAS_WHATSAPP_ALLOW_FROM=+569XXXXXXXX
```

### Vincular QR (telefono del numero OpenClaw)

Desde PC, SSH **interactivo** (`-t`):

```powershell
ssh -t mauro@192.168.1.12 "cd /home/mauro/openclaw-mauro/openclaw && docker compose exec openclaw-cli openclaw channels login --channel whatsapp --account default"
```

En el celular del **numero nuevo dedicado**: WhatsApp → Dispositivos vinculados → escanear QR.

### Comportamiento (= Telegram)

| Aspecto | Valor |
|---------|--------|
| Agente | `finanzas` (binding `channel: whatsapp`) |
| Grupos | deshabilitados |
| DMs | allowlist (tu numero) o pairing |
| Boletas foto | `receipt_vision_agent.py --latest-inbound --source whatsapp_foto` |
| Media inbound | `data/config/media/inbound/` (compartido) |

Verificar:

```bash
docker compose exec openclaw-cli openclaw channels status --deep
```

Si `dmPolicy=pairing`:

```bash
docker compose exec openclaw-cli openclaw pairing list whatsapp
docker compose exec openclaw-cli openclaw pairing approve whatsapp <CODIGO>
```

---

Pegar en config del agente o SOUL/skills:

```text
Eres agente finanzas personal de Mauricio (Chile, CLP).

Cuando llegue FOTO de boleta:
1. Confirmar que se guardo en data/inbox/boletas/
2. Ejecutar: python scripts/receipt_vision_agent.py --image <ruta> --source telegram_foto --source-ref <id> --merge
3. Responder: comercio, fecha, total, items principales, categoria

Para consultas de gastos:
- Leer data/finanzas_movimientos.csv
- Agrupar por mes, categoria, comercio
- Incluir transferencias Santander como movimientos aparte

No inventar montos. Si falta data, decir que falta.
```

---

## 8) Probar vision contra Iamiko

```powershell
python scripts/receipt_vision_agent.py --image "assets\boleta-simi.jpg" --source manual --merge --json
```

Respuesta esperada (JSON):

```json
{
  "status": "processed",
  "store": "FARMACIAS DEL DOCTOR SIMI",
  "ticket_total": 16840,
  "items_count": 4
}
```

---

## 9) Archivos del modulo

| Archivo | Funcion |
|---------|---------|
| `scripts/finanzas_common.py` | Esquema CSV, categorias, merge |
| `scripts/receipt_vision_agent.py` | Vision API + inbox |
| `scripts/finanzas_merge.py` | CSV unificado |
| `scripts/run_finanzas_pipeline.ps1` | Job Windows |
| `config/finanzas/openclaw-finanzas.example.json` | Snippet OpenClaw |

Scripts existentes que alimentan el merge:

- `scripts/lider_receipts_agent.py`
- `scripts/transferencias_agent.py`

---

## 10) Troubleshooting

| Sintoma | Causa | Fix |
|---------|-------|-----|
| Telegram "Something went wrong" con foto | Modelo sin vision | Enrutar foto a `finanzas` + fallback vision |
| Vision timeout | Modelo 30B lento | Subir timeout LiteLLM a 90s (ya en sync script) |
| Boleta duplicada | Misma foto reenviada | OK — `receipts_vision_state.json` la salta |
| Transferencias todas salida | Falta `FINANZAS_OWNER_RUT` | Setear RUT en `.env` |
| CSV vacio | Gmail no configurado | Ver `README-lider-agent.md` OAuth |
