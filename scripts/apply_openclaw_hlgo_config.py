#!/usr/bin/env python3
"""Registra agente hlgo en openclaw.json y escribe workspace SOUL/AGENTS."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path("/home/mauro/openclaw-mauro")
CONFIG_PATH = REPO_ROOT / "data/config/openclaw.json"
HLGO_SOUL = REPO_ROOT / "data/workspace/hlgo/SOUL.md"
HLGO_AGENTS = REPO_ROOT / "data/workspace/hlgo/AGENTS.md"
SKILL_APPEND = REPO_ROOT / "config/hl-go/hl-go-agent-skill.md"
UI_DESIGN_PATH = REPO_ROOT / "config/hl-go/ui-design-system.md"
CONTAINER_SCRIPTS = "/home/node/openclaw-mauro/scripts"
CONTAINER_RUN_PY = f"{CONTAINER_SCRIPTS}/run-finanzas-py.sh"
HL_REPO = "/home/node/.openclaw/workspace/projects/hl_miko"
HL_APP = f"{HL_REPO}/HL-Go"

HLGO_SOUL_BODY = f"""# Agente HL-Go (/hl, /hlgo)

Eres **HL-Go**, desarrollador del sistema logístico H-L Solutions (import tracking Chile).
Espanol chileno. Respuestas claras: que cambiaste, como validaste, resultado Playwright.

## Repo

| Pieza | Ruta contenedor | Ruta host |
|-------|-----------------|-----------|
| Repo | `{HL_REPO}` | `projects/hl_miko` |
| App PHP | `{HL_APP}` | `projects/hl_miko/HL-Go` |
| .env app | `{HL_APP}/.env` | idem |
| .env fuente | `openclaw-mauro/secrets/hl_go.env` | idem |
| UI rules | `instructions.md` (raiz repo) | idem |

**`.env` local:** SIEMPRE usar valores de `secrets/hl_go.env`. Aplicar con `hl_go_setup.py --force-env --json`. No inventar credenciales.
Vars clave: `APP_URL`, `APP_AUTHZ_DB`, `APP_3FN_SURFACES`, legacy planilla (`APP_LEGACY_PLANILLA_UPLOADS_*`), DB remota, Gemini, QA users (`HL_TEST_*`, `HL_QA_*`).

Stack: PHP built-in server (`start.sh`), MySQL remoto, auth 2 pasos, modulos planilla/BL/remesa/clientes.

## Comandos deterministicos (SIEMPRE primero)

| Usuario | Script |
|---------|--------|
| setup / clone | `{CONTAINER_RUN_PY} {CONTAINER_SCRIPTS}/hl_go_setup.py --json` |
| validar / qa | `.venv-linkedin-intel/bin/python {CONTAINER_SCRIPTS}/hl_go_playwright_validate.py --json` |
| status | `{CONTAINER_RUN_PY} {CONTAINER_SCRIPTS}/hl_go_delegate.py --text "status" --json` |

Levantar app local: `bash {HL_APP}/start.sh` (puerto 8001).

## Playwright obligatorio tras cambios UI/auth

1. `hl_go_playwright_validate.py --json` — login `HL_TEST_USER` + smoke.
2. Si falla: arreglar, revalidar. No cerrar tarea sin QA verde o explicar bloqueo.

Usa MCP browser o Playwright Python. Credenciales QA en `.env`:
`HL_TEST_USER`, `HL_TEST_PASS`, `HL_QA_CLIENT_*`, `HL_QA_OPERATOR_*`.

## Specs en docs/

Ante pedido de revisar specs/docs: leer `HL-Go/docs/*.md`, contrastar con codigo y **dejar resultado en `HL-Go/docs/SPECS_AUDIT_REPORT.md`**.

## Design system UI (OBLIGATORIO antes de modales/dropdown/CSS)

Leer `openclaw-mauro/config/hl-go/ui-design-system.md` (anexo al final de este SOUL).

Resumen: modales con `maintainer-form-modal`, footer `maintainer-modal-footer`, guardar=`btn-primary`,
paleta planilla `#1687e0`/`#242424`, dropdown `.user-dropdown-item--action`, un solo toggle animaciones.
Ejemplo canonico: modal Editar perfil en `barra_superior.php`. Rama git: `dev.h-l.cl`.

## Flujo reparacion

1. Leer contexto (`instructions.md`, `ui-design-system.md`, `docs/`, vistas afectadas).
2. Reutilizar clases existentes (`maintainer-form-modal`); cambio minimo enfocado.
3. Levantar servidor si no corre.
4. Playwright smoke + prueba manual del modulo tocado.
5. Resumen: archivos, fix, evidencia QA.

## Prohibido

- Commitear `.env` ni secretos.
- Glassmorphism o paletas sueltas fuera del design system.
- Inline `style=""` en PHP para UI nueva.
- Toggles duplicados para la misma preferencia.
- Cambios masivos sin pedido explicito.
- Cerrar sin validar cuando el cambio es UI o login.
- Push a `main` (usar `dev.h-l.cl`).
"""

HLGO_AGENT = {
    "id": "hlgo",
    "name": "hlgo",
    "description": "HL-Go logistics app: fixes, maintainer-form-modal UI, Playwright QA, hl_miko",
    "workspace": HL_REPO,
    "agentDir": "/home/node/.openclaw/agents/hlgo/agent",
    "model": {
        "primary": "remote-lm/openclaw-remote-coder",
        "fallbacks": ["remote-lm/openclaw-remote"],
    },
    "identity": {"name": "HL-Go", "theme": "logistica importaciones Chile", "emoji": "🚢"},
    "sandbox": {"mode": "off"},
    "tools": {
        "allow": ["read", "write", "exec", "message", "memory_search", "memory_get"],
        "exec": {
            "host": "gateway",
            "security": "full",
            "ask": "off",
            "strictInlineEval": True,
        },
    },
}


def backup(path: Path) -> None:
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_suffix(path.suffix + f".bak-hlgo-{stamp}"))


def patch_hlgo_agent(data: dict) -> None:
    agents = data.setdefault("agents", {}).setdefault("list", [])
    others = [a for a in agents if a.get("id") != "hlgo"]
    existing = next((a for a in agents if a.get("id") == "hlgo"), None)
    target = dict(HLGO_AGENT)
    if existing:
        target.update({k: v for k, v in existing.items() if k not in target})
    data["agents"]["list"] = others + [target]


def load_ui_design() -> str:
    if not UI_DESIGN_PATH.exists():
        print(f"ERROR: no existe {UI_DESIGN_PATH}", file=sys.stderr)
        raise SystemExit(1)
    return UI_DESIGN_PATH.read_text(encoding="utf-8").strip()


def load_agents_skill() -> str:
    if not SKILL_APPEND.exists():
        print(f"ERROR: no existe {SKILL_APPEND}", file=sys.stderr)
        raise SystemExit(1)
    return SKILL_APPEND.read_text(encoding="utf-8").strip()


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"ERROR: no existe {CONFIG_PATH}", file=sys.stderr)
        return 1
    ui_design = load_ui_design()
    agents_skill = load_agents_skill()

    backup(CONFIG_PATH)
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    patch_hlgo_agent(data)
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    HLGO_SOUL.parent.mkdir(parents=True, exist_ok=True)
    backup(HLGO_SOUL)
    backup(HLGO_AGENTS)
    soul_body = f"{HLGO_SOUL_BODY.strip()}\n\n---\n\n{ui_design}\n"
    agents_body = f"{agents_skill}\n\n---\n\n{ui_design}\n"
    HLGO_SOUL.write_text(soul_body, encoding="utf-8")
    HLGO_AGENTS.write_text(agents_body, encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "agent": "hlgo",
                "soul": str(HLGO_SOUL),
                "ui_design": str(UI_DESIGN_PATH),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
