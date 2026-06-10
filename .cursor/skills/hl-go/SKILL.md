---
name: hl-go
description: >-
  Agente HL-Go para reparar y desarrollar hl_miko (logistica importaciones Chile):
  clone/setup repo, .env local, fixes PHP, UI con design system maintainer-form-modal,
  validacion Playwright obligatoria. Usar con /hl, /hlgo, /hl-go, HL-Go, planilla,
  remesa, BL, hl_miko, modal, dropdown usuario, editar perfil.
---

# HL-Go — agente desarrollo

Espanol chileno. Cambio minimo + design system HL-Go + Playwright antes de cerrar.

## Rutas

| Pieza | Host | Contenedor OpenClaw |
|-------|------|---------------------|
| Repo | `projects/hl_miko` | `/home/node/.openclaw/workspace/projects/hl_miko` |
| App | `projects/hl_miko/HL-Go` | `.../HL-Go` |
| Secrets env | `secrets/hl_go.env` | idem |
| UI rules | `instructions.md` | raiz repo |
| **Design system UI** | `config/hl-go/ui-design-system.md` | idem |

Repo remoto: `https://github.com/Maurog-castros/hl_miko.git` — rama **`dev.h-l.cl`**.

## Setup inicial

```bash
python3 scripts/hl_go_setup.py --json
python3 scripts/apply_openclaw_hlgo_config.py
```

`hl_go_setup.py`: symlink workspace, escribe `HL-Go/.env` desde `secrets/hl_go.env`, pull si hay `.git`.

**`.env` canonico:** `secrets/hl_go.env` → copiar a `HL-Go/.env` con `--force-env`. No inventar credenciales.

## Sistema de diseño UI (OBLIGATORIO)

**Antes de modales, dropdown, CSS o prefs de usuario → leer [ui-design-system.md](../../config/hl-go/ui-design-system.md).**

Resumen rapido:

1. Modales: `modern-modal` + **`maintainer-form-modal`** (misma estetica planilla).
2. Footer: `maintainer-modal-footer` / `maintainer-modal-footer__end`.
3. Guardar = `btn-primary`, Cancelar = `btn-secondary`.
4. CSS scoped (`.mi-modal.maintainer-form-modal`), **sin inline styles** en PHP.
5. Paleta planilla: `#1687e0`, `#242424`, `#1f1f1f`, `#94a3b8`.
6. Dropdown: `.user-dropdown-controls` + `.user-dropdown-item--action`.
7. Animaciones: **un solo** `#planilla-animation-toggle`; migrar `miko-motion-paused` si aplica.
8. Light theme: overrides `[data-theme="light"]` en cada feature nueva.

Referencia viva: modal perfil en `barra_superior.php` (commits `77d8b47`, `0acc2c9`).

Detalle archivos: [reference.md](reference.md)

## Servidor dev

```bash
bash projects/hl_miko/HL-Go/start.sh
# http://localhost:8001
```

## QA Playwright (obligatorio tras UI/auth)

```bash
.venv-linkedin-intel/bin/python scripts/hl_go_playwright_validate.py --json
```

Login 2 pasos: `#user` → `#btn-next` → `#pass` → submit.

## WhatsApp / OpenClaw

```bash
./scripts/run-finanzas-py.sh scripts/hl_go_delegate.py --text "<msg>" --json
```

Prefijos: `/hl`, `/hlgo`, `/hl-go`. Subcomandos: `setup`, `validar`, `status`.

## Auditoría specs (`docs/`)

Leer `HL-Go/docs/*.md`, contrastar codigo, escribir **`HL-Go/docs/SPECS_AUDIT_REPORT.md`**.

## Flujo fix

1. Leer `instructions.md` + **`ui-design-system.md`** si toca UI.
2. Buscar patron existente (`maintainer-form-modal`, modulos planilla).
3. Patch minimo; reutilizar clases, no inventar paleta.
4. Servidor + Playwright smoke.
5. Reportar archivos + resultado QA.

## Prohibido

- Commitear `.env` ni `secrets/hl_go.env`.
- Glassmorphism / paletas sueltas fuera del design system.
- Inline `style=""` en PHP para UI nueva.
- Toggles duplicados para la misma preferencia.
- Cerrar tarea UI sin Playwright o bloqueo documentado.
- Push a `main` (usar `dev.h-l.cl`).
