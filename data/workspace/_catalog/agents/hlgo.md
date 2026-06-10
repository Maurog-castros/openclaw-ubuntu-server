# Agente `hlgo` 🚢

**Descripción:** HL-Go logistics app — fixes PHP, UI, Playwright QA en hl_miko.

## Repo Git

Monorepo: `/home/node/.openclaw/workspace/projects/hl_miko` (`.git` en la raíz, no en `openclaw-mauro`).

```sh
git -C /home/node/.openclaw/workspace/projects/hl_miko pull --ff-only
```

WhatsApp: `/hlgo pull` o `/hlgo actualizar repo` → delegate determinístico.

## Qué hace

- Setup/pull repo: `hl_go_setup.py --json`
- Desarrollo UI siguiendo `config/hl-go/ui-design-system.md`
- Validación Playwright: `hl_go_playwright_validate.py --json`
- Módulos: planilla, bl, remesa, clients, catalogs, generator, navieras, puertos, landing, auth
- Git: rama **`dev.h-l.cl`** (no `main`)

## Workspace

`/home/node/.openclaw/workspace/projects/hl_miko` (comparte repo con hl-miko-web)  
Detalle: `hlgo/AGENTS.md`, código en `HL-Go/`
