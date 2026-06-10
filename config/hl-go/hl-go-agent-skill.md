# AGENTS.md — HL-Go

## Workflow

1. Sin repo → `hl_go_setup.py --json` (clone + .env).
2. Antes de codificar UI → leer `instructions.md` + **`config/hl-go/ui-design-system.md`**.
3. Servidor dev → `bash HL-Go/start.sh` en `/home/node/.openclaw/workspace/projects/hl_miko/HL-Go`.
4. Tras cada fix UI/auth → `hl_go_playwright_validate.py --json`.
5. Usuarios QA en `.env` para roles distintos.
6. Git: rama **`dev.h-l.cl`** (no `main`).

## Modulos clave

`planilla`, `bl`, `remesa`, `clients`, `catalogs`, `generator`, `navieras`, `puertos`, `landing`, `auth`.

## Estructura PHP

- `HL-Go/public/index.php` — router
- `HL-Go/src/Services/` — logica
- `HL-Go/src/Repositories/` — DB
- `HL-Go/src/Views/` — vistas
- `HL-Go/assets/` — CSS/JS
- `HL-Go/src/Presentation/Legacy/Principales/barra_superior.php` — header, dropdown, modales globales

## Estilo operacional

Alta densidad, tablas soft-grid (ver `instructions.md`). NO marketing UI.

## Design system UI (resumen)

Ver documento completo: `config/hl-go/ui-design-system.md`

- Modales formulario: `modern-modal` + `maintainer-form-modal`
- Footer: `maintainer-modal-footer` / `maintainer-modal-footer__end`
- Guardar = `btn-primary`, Cancelar = `btn-secondary`
- Paleta planilla: `#1687e0`, `#242424`, `#1f1f1f`, `#94a3b8`
- Dropdown: `.user-dropdown-controls`, `.user-dropdown-item--action`, sin inline styles
- Animaciones: un solo `#planilla-animation-toggle`; migrar `miko-motion-paused`
- Ejemplo canonico: modal Editar perfil en `barra_superior.php`
