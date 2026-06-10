# Catálogo de agentes OpenClaw — Mauro

Directorio compartido de lectura para **todos** los agentes. Mismo volumen Docker (`/home/node/.openclaw/workspace`).

Cuando un usuario pregunte qué hace otro agente, **lee el archivo de ese agente aquí** (no inventes rutas como `/app/docs/agents/*.md`).

## Índice rápido

| ID | Prefijo | Emoji | Resumen | Archivo |
|----|---------|-------|---------|---------|
| `main` | — | — | Orquestador general, host Docker, repos | [main.md](main.md) |
| `care` | `/care` | 🌿 | Diario personal, salud, ánimo, medicamentos | [care.md](care.md) |
| `fin` | `/fin` | 💰 | Gastos, boletas, transferencias, saldo banco | [fin.md](fin.md) |
| `supp` | `/supp` | 🛠 | Soporte técnico OpenClaw, logs, remediación | [supp.md](supp.md) |
| `intel` | `/intel` | — | Radar tendencias DevOps, leads, YouTube | [intel.md](intel.md) |
| `content` | `/content` | — | Borradores LinkedIn, carruseles, ebooks | [content.md](content.md) |
| `sales` | — | — | Pipeline comercial, outreach desde leads Intel | [sales.md](sales.md) |
| `jobs` | — | 📋 | Postulaciones LinkedIn, CV match, Easy Apply | [jobs.md](jobs.md) |
| `hlgo` | `/hlgo`, `/hl` | 🚢 | App HL-Go logística (PHP, Playwright QA) | [hlgo.md](hlgo.md) |
| `hl-miko-web` | — | 🛠️ | Desarrollo web hl_miko (HL-Go, APIs) | [hl-miko-web.md](hl-miko-web.md) |
| `pyme-chile` | — | — | Concursos y fondos para pymes Chile | [pyme-chile.md](pyme-chile.md) |

## Enrutado WhatsApp/Telegram

Canal → agente **`main`** → `channel_delegate.py` detecta intención y deriva:

- saldo, boletas, movimientos → **fin**
- ánimo, salud, medicamentos → **care**
- logs, fixes, soporte → **supp**
- tendencias, radar → **intel**
- Instagram, contenido → **content**
- HL-Go, pull repo, QA logística → **hlgo**

Los prefijos `/fin`, `/care`, `/supp`, `/intel`, `/content`, `/hlgo` (y `/hl`) siguen funcionando (legacy `/finanzas` → fin).

## Workspaces privados (detalle operativo)

Cada agente tiene su workspace con `AGENTS.md`, `SOUL.md`, memoria y datos sensibles. El catálogo es **solo lectura compartida**; no reemplaza esos archivos.

| Agente | Workspace |
|--------|-----------|
| main | `/home/node/.openclaw/workspace` |
| care | `/home/node/.openclaw/workspace/care` |
| fin | `/home/node/.openclaw/workspace/marketing/finanzas` |
| supp | `/home/node/.openclaw/workspace/support` |
| intel | `/home/node/.openclaw/workspace/marketing/intel` |
| content | `/home/node/.openclaw/workspace/marketing/content` |
| sales | `/home/node/.openclaw/workspace/marketing/sales` |
| jobs | `/home/node/.openclaw/workspace/jobs` |
| hlgo, hl-miko-web | `/home/node/.openclaw/workspace/projects/hl_miko` |
| pyme-chile | `/home/node/.openclaw/workspace/pyme-chile` |

## Alexa

Skill **care** → agente `care` vía Lambda (`openclaw/care`). Sesiones: `alexa:{userId}:care`.
