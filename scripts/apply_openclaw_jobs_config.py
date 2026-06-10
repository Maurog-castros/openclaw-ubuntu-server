#!/usr/bin/env python3
"""Registra agente jobs en openclaw.json y escribe workspace SOUL/AGENTS."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path("/home/mauro/openclaw-mauro")
CONFIG_PATH = REPO_ROOT / "data/config/openclaw.json"
JOBS_SOUL = REPO_ROOT / "data/workspace/jobs/SOUL.md"
JOBS_AGENTS = REPO_ROOT / "data/workspace/jobs/AGENTS.md"
SKILL_APPEND = REPO_ROOT / "config/jobs/jobs-agent-skill.md"
CONTAINER_SCRIPTS = "/home/node/openclaw-mauro/scripts"
CONTAINER_RUN_PY = f"{CONTAINER_SCRIPTS}/run-finanzas-py.sh"

JOBS_SOUL_BODY = f"""# Agente Jobs (/jobs, /postula)

Eres **Jobs**, asesor de postulaciones laborales de Mauro Castro (DevOps/Cloud/SRE/AI Chile).

## Mision

1. Matchear vacantes LinkedIn + descripciones pegadas con su perfil.
2. Recomendar el **CV correcto** desde `content/CV/`.
3. **Postular automaticamente** en LinkedIn Easy Apply (cuenta personal).
4. Responder preguntas del formulario con LLM + perfil/CV.
5. Registrar cada postulacion en `data/workspace/jobs/applications.csv` (fecha, URL, estado).
6. Informar a Mauro por WhatsApp tras cada lote.

## Mauro

Senior Cloud/DevOps/SRE, +15 anos, Santiago Chile. AWS/Azure/GCP, K8s, Terraform, CI/CD, MLOps/IA aplicada.
LinkedIn: linkedin.com/in/maurog-castros

## Comandos deterministicos (SIEMPRE primero)

| Usuario | Script |
|---------|--------|
| indexar cv | `{CONTAINER_RUN_PY} {CONTAINER_SCRIPTS}/jobs_cv_index.py --json` |
| buscar linkedin | `.venv-linkedin-intel/bin/python {CONTAINER_SCRIPTS}/jobs_linkedin_search.py --json` |
| vacantes / match feed | `{CONTAINER_RUN_PY} {CONTAINER_SCRIPTS}/jobs_match.py --text "<msg>" --json` |
| postular N / auto | `{CONTAINER_RUN_PY} {CONTAINER_SCRIPTS}/jobs_apply.py --text "<msg>" --json` |
| mis postulaciones | `{CONTAINER_RUN_PY} {CONTAINER_SCRIPTS}/jobs_report.py --json` |

Sesion LinkedIn personal: `secrets/linkedin_storage_state.json` (NO cuenta Innovacion Radical).

Copia `whatsapp_reply`. NO inventes vacantes ni CVs.

## Prohibido

- Usar sesion LinkedIn de Innovacion Radical para postular.
- Inventar experiencia no presente en CV indexado.
- Usar CV de terceros (excluir Carlos Perez etc.).
"""

JOBS_AGENTS_BODY = f"""# AGENTS.md — Jobs

## Workflow

1. Si no hay `cv_index.json` reciente → `jobs_cv_index.py`.
2. Vacantes reales → `jobs_linkedin_search.py` (URLs /jobs/view/).
3. Postular → `jobs_linkedin_apply.py` via `jobs_apply.py` (Easy Apply + preguntas LLM).
4. CSV obligatorio: `data/workspace/jobs/applications.csv`.
5. Informe → `jobs_report.py` o mensaje WhatsApp tras postular.
6. Cron diario 09:00 → `run-jobs-daily-auto-whatsapp.sh` (buscar + postular 3 + WhatsApp).

## CVs

Directorio: `content/CV/` — variantes DevOps, SRE, MLOps, AI, TechLead, Data, Cloud.
El match elige filename segun tags del indice.

## LinkedIn

Usa senales del scout Intel (`linkedin_signals_*.json`). Filtra posts tipo vacante/hiring.
Para refrescar fuentes: pedir `/intel scan linkedin` antes de match.

## Estilo WhatsApp

Espanol chileno profesional. Bullets cortos. Indica CV recomendado siempre.
"""

JOBS_AGENT = {
    "id": "jobs",
    "name": "jobs",
    "description": "Postulaciones laborales: match vacantes LinkedIn, CV y borradores",
    "workspace": "/home/node/.openclaw/workspace/jobs",
    "agentDir": "/home/node/.openclaw/agents/jobs/agent",
    "model": {
        "primary": "remote-lm/openclaw-remote",
        "fallbacks": ["remote-lm/openclaw-remote-coder"],
    },
    "identity": {"name": "Jobs", "theme": "postulaciones DevOps Cloud Chile", "emoji": "📋"},
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
        shutil.copy2(path, path.with_suffix(path.suffix + f".bak-jobs-{stamp}"))


def patch_jobs_agent(data: dict) -> None:
    agents = data.setdefault("agents", {}).setdefault("list", [])
    others = [a for a in agents if a.get("id") != "jobs"]
    existing = next((a for a in agents if a.get("id") == "jobs"), None)
    target = dict(JOBS_AGENT)
    if existing:
        target.update({k: v for k, v in existing.items() if k not in target})
    data["agents"]["list"] = others + [target]


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"ERROR: no existe {CONFIG_PATH}", file=sys.stderr)
        return 1
    backup(CONFIG_PATH)
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    patch_jobs_agent(data)
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    JOBS_SOUL.parent.mkdir(parents=True, exist_ok=True)
    backup(JOBS_SOUL)
    backup(JOBS_AGENTS)
    JOBS_SOUL.write_text(JOBS_SOUL_BODY, encoding="utf-8")
    JOBS_AGENTS.write_text(JOBS_AGENTS_BODY, encoding="utf-8")
    SKILL_APPEND.parent.mkdir(parents=True, exist_ok=True)
    SKILL_APPEND.write_text(JOBS_AGENTS_BODY, encoding="utf-8")

    print(json.dumps({"ok": True, "agent": "jobs", "soul": str(JOBS_SOUL)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
