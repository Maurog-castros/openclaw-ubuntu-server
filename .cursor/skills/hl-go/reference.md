# Referencia HL-Go — UI y archivos clave

Documento completo: [config/hl-go/ui-design-system.md](../../config/hl-go/ui-design-system.md)

## Clases CSS obligatorias (modales)

- `modern-modal` + `maintainer-form-modal`
- Footer: `maintainer-modal-footer` → `maintainer-modal-footer__end`
- Guardar: `btn-primary btn-modal-action` | Cancelar: `btn-secondary btn-modal-action`
- Inputs: `modern-input` en `.form-group` dentro de `.form-grid`

## Paleta (no inventar otra)

`#1687e0` accent · `#242424` superficie · `#1f1f1f` input · `#94a3b8` muted

## Dropdown usuario

- `.user-dropdown-controls` — fondo + animaciones (header)
- `.user-dropdown-item--action` — acciones (sin inline style)
- Un solo toggle: `#planilla-animation-toggle` (+ migración `miko-motion-paused`)

## Archivos de referencia en hl_miko

| Qué | Ruta |
|-----|------|
| Modal perfil (ejemplo correcto) | `HL-Go/src/Presentation/Legacy/Principales/barra_superior.php` |
| CSS maintainer + perfil | `HL-Go/assets/css/main.app.css` |
| Estilos maintainer base | buscar `.modern-modal.maintainer-form-modal` en `main.app.css` |
| API perfil | `HL-Go/src/Controllers/UserController.php` → `selfProfile()` |
| Rutas | `HL-Go/config/page_routes.php` → `profile_self` |
| UI rules generales | `instructions.md` (raíz repo) |
| Specs | `HL-Go/docs/*.md` → informe en `SPECS_AUDIT_REPORT.md` |

## Rama git

Publicar en **`dev.h-l.cl`** (rama activa del proyecto). `main` está obsoleto.

## QA

```bash
.venv-linkedin-intel/bin/python scripts/hl_go_playwright_validate.py --json
```
