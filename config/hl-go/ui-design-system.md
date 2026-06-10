# HL-Go — Sistema de diseño UI (convenciones Mauro)

**Obligatorio leer antes de tocar modales, dropdown usuario, CSS o JS de preferencias.**

Fuente de verdad visual: modales planilla/maintainers (`maintainer-form-modal`, `miko-modal--acciones`).
NO inventar glassmorphism ni paletas sueltas con `var(--accent-blue)` sin contexto.

## Principios

1. **Componer, no reinventar** — enganchar clases existentes del proyecto.
2. **CSS con modificadores** — cero `style="..."` inline en PHP.
3. **Un control = un estado** — no duplicar toggles para la misma preferencia.
4. **Migrar localStorage** — compatibilidad con claves viejas al renombrar prefs.
5. **Light + dark** — cada feature nueva necesita overrides `[data-theme="light"]`.
6. **Validar con Playwright** — tras cualquier cambio UI.

---

## Paleta planilla / maintainer (`miko-modal--acciones`)

| Token | Valor | Uso |
|-------|-------|-----|
| Accent | `#1687e0` | botón primario, focus input, icono título |
| Accent hover | `#1a93f0` | hover primario |
| Superficie | `#242424` | botones secundarios, avatar bg |
| Superficie hover | `#2d2d2d` | hover secundario |
| Borde | `#3f3f3f` / `#3d3d3d` | inputs, botones |
| Input bg | `#1f1f1f` | campos oscuros |
| Texto | `#ececec` / `#f2f2f2` | labels activos |
| Texto muted | `#94a3b8` | labels, hints |
| Input texto | `#d6d6d6` | valor en campos |

Light theme: seguir patrón existente en `main.app.css`:

```css
[data-theme="light"] .mi-modal.maintainer-form-modal .modern-input,
html:not([data-theme="dark"]) .mi-modal.maintainer-form-modal .modern-input { ... }
```

---

## Modales de formulario

### Estructura HTML (plantilla)

```html
<div class="modern-modal {feature}-modal maintainer-form-modal" id="{feature}Modal" aria-hidden="true">
  <div class="overlay" id="{feature}Overlay"></div>
  <div class="modern-modal-content {feature}-modal__content">
    <div class="modern-modal-header">
      <div class="modal-title-wrap">
        <span class="modal-title-icon"><i class="fa fa-..."></i></span>
        <div class="modal-title-text">
          <h3>Título</h3>
          <p class="modal-title-sub">Subtítulo corto</p>
        </div>
      </div>
      <button type="button" class="modern-modal-close" aria-label="Cerrar">...</button>
    </div>
    <div class="modern-modal-body">
      <div class="form-grid {feature}-form-grid">...</div>
    </div>
    <div class="modern-modal-footer maintainer-modal-footer">
      <div class="maintainer-modal-footer__end">
        <button type="button" class="btn-secondary btn-modal-action" id="{feature}Cancel">Cancelar</button>
        <button type="button" class="btn-primary btn-modal-action" id="{feature}Save">
          <i class="fa fa-save"></i> Guardar cambios
        </button>
      </div>
    </div>
  </div>
</div>
```

### Reglas

- Clase base: `modern-modal` + `maintainer-form-modal`.
- Footer: `maintainer-modal-footer` + `maintainer-modal-footer__end` (botones alineados a la derecha).
- **Guardar** = `btn-primary`. **Cancelar** = `btn-secondary`. Nunca ambos secundarios.
- Inputs: clase `modern-input` dentro de `.form-group`.
- Overrides CSS scoped: `.{feature}-modal.maintainer-form-modal .modern-input` (no estilos globales sueltos).
- Referencia viva: modal perfil en `barra_superior.php` (`profile-self-modal`).

### Ejemplo real (perfil propio)

- PHP: `HL-Go/src/Presentation/Legacy/Principales/barra_superior.php`
- CSS: `HL-Go/assets/css/main.app.css` (bloque `/* Perfil propio — paleta miko-modal--acciones */`)
- API: `UserController::selfProfile()` + `UserProfileService`

---

## Menú dropdown usuario

Archivo: `barra_superior.php` + estilos `.user-dropdown*` en `main.app.css`.

### Layout (3 zonas)

1. **Header** (`.user-dropdown-header`) — avatar, nombre, última conexión.
2. **Controles** (`.user-dropdown-controls`) — fondo app + toggle animaciones, centrados.
3. **Acciones** (`.user-dropdown-body`) — Editar perfil, Cerrar sesión.

### Clases

| Clase | Uso |
|-------|-----|
| `.user-dropdown` | panel flotante (260px, centrado, `text-align: center`) |
| `.user-dropdown-controls` | bloque vertical de preferencias (fondo + animaciones) |
| `.user-dropdown-item` | fila de menú centrada (`inline-flex`, `justify-content: center`) |
| `.user-dropdown-item--action` | botón o link de acción (sin inline styles) |

### Prohibido en dropdown

- `style="width:100%; border:none; ..."` en botones — usar `--action`.
- Segundo toggle redundante para la misma preferencia.

---

## Preferencias de animación (un solo toggle)

**Un único control:** `#planilla-animation-toggle` (switch ON/OFF en dropdown).

### localStorage

| Clave | Valor | Significado |
|-------|-------|-------------|
| `planilla-animations-enabled` | `'1'` / `'0'` | preferencia canónica |
| `miko-motion-paused` | `'1'` | **legacy** — leer solo si la clave nueva no existe |

### Bootstrap (al cargar página)

```javascript
if (localStorage.getItem('planilla-animations-enabled') === '0'
    || localStorage.getItem('miko-motion-paused') === '1') {
  document.documentElement.classList.add('planilla-animations-disabled');
  document.documentElement.classList.add('miko-motion-paused');
}
```

### Al cambiar toggle

```javascript
function readEnabled() {
  if (localStorage.getItem('planilla-animations-enabled') !== null) {
    return localStorage.getItem('planilla-animations-enabled') !== '0';
  }
  return localStorage.getItem('miko-motion-paused') !== '1';
}

function applyAnimationPreference(enabled) {
  document.documentElement.classList.toggle('planilla-animations-disabled', !enabled);
  document.documentElement.classList.toggle('miko-motion-paused', !enabled);
}

// on change:
localStorage.setItem('planilla-animations-enabled', enabled ? '1' : '0');
localStorage.removeItem('miko-motion-paused');
```

**No crear** un `motion-toggle` separado. Las dos clases CSS deben sincronizarse desde un solo switch.

---

## Archivos habituales por tipo de cambio

| Cambio | Archivos |
|--------|----------|
| Modal nuevo | `barra_superior.php` o vista del módulo, `main.app.css`, Service + Controller |
| Dropdown usuario | `barra_superior.php`, `main.app.css` (`.user-dropdown*`) |
| Estilos planilla/modal | `main.app.css` (buscar `maintainer-form-modal`, `miko-modal--acciones`) |
| Rutas API perfil | `HL-Go/config/page_routes.php`, `UserController.php` |
| JS modal perfil | inline en `barra_superior.php` (patrón IIFE existente) |

---

## Checklist antes de cerrar tarea UI

- [ ] ¿Usé `maintainer-form-modal` en lugar de estilos custom sueltos?
- [ ] ¿Botón guardar es `btn-primary`?
- [ ] ¿Sin `style=""` inline en PHP?
- [ ] ¿Overrides light theme si toqué colores?
- [ ] ¿Un solo toggle por preferencia de usuario?
- [ ] ¿Migración localStorage si renombré clave?
- [ ] `hl_go_playwright_validate.py --json` en verde
- [ ] Screenshot o evidencia del módulo tocado

---

## Anti-patrones (no repetir)

| Mal | Bien |
|-----|------|
| Modal con solo `profile-self-modal` + glass blur genérico | `profile-self-modal maintainer-form-modal` |
| Guardar con `btn-secondary` | Guardar con `btn-primary` |
| Pill azul `var(--accent-blue)` en acciones secundarias | Botón `#242424` borde `#3f3f3f` |
| Dos toggles animación (`motion-toggle` + `planilla-animation-toggle`) | Solo `planilla-animation-toggle` |
| CSS global sin scope | `.mi-feature-modal.maintainer-form-modal .elemento` |
| Cerrar sin Playwright | Smoke obligatorio post-cambio |
