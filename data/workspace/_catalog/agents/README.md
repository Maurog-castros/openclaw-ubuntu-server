# Catálogo de agentes OpenClaw — Mauro

Directorio compartido de lectura para **todos** los agentes. Mismo volumen Docker (`/home/node/.openclaw/workspace`).

Cuando un usuario pregunte qué hace otro agente, **lee el archivo de ese agente aquí** (no inventes rutas como `/app/docs/agents/*.md`).

**13 agentes** registrados en el gateway OpenClaw (junio 2026).

## Índice rápido

| ID | Prefijo | Emoji | Resumen | Archivo |
|----|---------|-------|---------|---------|
| `main` | — | — | Orquestador general, host Docker, repos | [main.md](main.md) |
| `care` | `/care` | 🌿 | Diario personal, salud, ánimo, medicamentos | [care.md](care.md) |
| `fin` | `/fin` | 💰 | Gastos, boletas, transferencias, saldo banco | [fin.md](fin.md) |
| `broh` | `/broh` | — | Compañía narrativa, memoria de historias, pulso | [broh.md](broh.md) |
| `supp` | `/supp` | 🛠 | Soporte técnico OpenClaw, logs, remediación | [supp.md](supp.md) |
| `intel` | `/intel` | — | Radar tendencias DevOps, leads, YouTube | [intel.md](intel.md) |
| `content` | `/content` | — | Borradores LinkedIn, carruseles, ebooks | [content.md](content.md) |
| `jobs` | `/jobs`, `/postula` | 📋 | Postulaciones LinkedIn, CV match, Easy Apply | [jobs.md](jobs.md) |
| `hlgo` | `/hlgo`, `/hl` | 🚢 | App HL-Go logística (PHP, Playwright QA) | [hlgo.md](hlgo.md) |
| `jenki` | `/jenki` | — | Jenkins CI/CD — builds, logs, cola vía `jk` | [jenki.md](jenki.md) |
| `pyme-chile` | `/pyme` | — | Concursos y fondos para pymes Chile | [pyme-chile.md](pyme-chile.md) |
| `sales` | — | — | Pipeline comercial, outreach desde leads Intel | [sales.md](sales.md) |
| `hl-miko-web` | — | 🛠️ | Desarrollo web hl_miko (HL-Go, APIs) | [hl-miko-web.md](hl-miko-web.md) |

Agentes **sin prefijo WhatsApp** (`sales`, `hl-miko-web`): Mission Control o sesiones LLM directas. El resto admite prefijo, hilo sticky o detección por intención.

## Enrutado WhatsApp/Telegram

Canal → agente **`main`** → `channel_delegate.py` detecta intención y deriva:

- saldo, boletas, movimientos → **fin**
- ánimo, salud, medicamentos → **care**
- compañía, perspectiva narrativa → **broh**
- logs, fixes, soporte → **supp**
- tendencias, radar → **intel**
- Instagram, contenido → **content**
- postulaciones, vacantes, CV → **jobs**
- HL-Go, pull repo, QA logística → **hlgo**
- Jenkins, pipelines, CI/CD → **jenki**
- fondos pyme, concursos → **pyme-chile**

Prefijos explícitos: `/fin`, `/care`, `/broh`, `/supp`, `/intel`, `/content`, `/jobs`, `/postula`, `/hlgo`, `/hl`, `/jenki`, `/pyme` (legacy `/finanzas` → fin, `/PymeChile` → pyme-chile).

Hilo **sticky**: mensajes sin prefijo continúan en el mismo agente hasta `/new`, `/reset` u otro prefijo.

## Workspaces privados (detalle operativo)

Cada agente tiene su workspace con `AGENTS.md`, `SOUL.md`, memoria y datos sensibles. El catálogo es **solo lectura compartida**; no reemplaza esos archivos.

| Agente | Workspace |
|--------|-----------|
| main | `/home/node/.openclaw/workspace` |
| care | `/home/node/.openclaw/workspace/care` |
| fin | `/home/node/.openclaw/workspace/marketing/finanzas` |
| broh | `/home/node/.openclaw/workspace/broh` |
| supp | `/home/node/.openclaw/workspace/support` |
| intel | `/home/node/.openclaw/workspace/marketing/intel` |
| content | `/home/node/.openclaw/workspace/marketing/content` |
| sales | `/home/node/.openclaw/workspace/marketing/sales` |
| jobs | `/home/node/.openclaw/workspace/jobs` |
| hlgo, hl-miko-web | `/home/node/.openclaw/workspace/projects/hl_miko` |
| jenki | `/home/node/.openclaw/workspace-jenki` |
| pyme-chile | `/home/node/.openclaw/workspace/pyme-chile` |

## Alexa

Skill **care** → agente `care` vía Lambda (`openclaw/care`). Sesiones: `alexa:{userId}:care`.
