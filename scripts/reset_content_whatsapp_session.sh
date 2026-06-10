#!/usr/bin/env bash
# Resetea sesión WhatsApp del agente content (context overflow / sesión vieja).
set -eu
REPO="${OPENCLAW_REPO:-/home/mauro/openclaw-mauro}"
SESSIONS_JSON="$REPO/data/config/agents/content/sessions/sessions.json"
KEY="agent:content:main"
STAMP="$(date +%Y%m%d-%H%M%S)"

cp "$SESSIONS_JSON" "${SESSIONS_JSON}.bak-reset-${STAMP}"
python3 <<PY
import json
from pathlib import Path
REPO = Path("$REPO")
path = REPO / "data/config/agents/content/sessions/sessions.json"
data = json.loads(path.read_text(encoding="utf-8"))
entry = data.pop("$KEY", None)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if entry:
    sid = entry.get("sessionId", "")
    print("removed", "$KEY", "sid=", sid)
    for base in [REPO / "data/config/agents/content/sessions"]:
        jl = base / f"{sid}.jsonl"
        if jl.exists():
            jl.rename(jl.with_suffix(f".jsonl.bak-reset-{STAMP}"))
            print("archived", jl)
PY
echo "Listo. Prueba de nuevo por WhatsApp."
