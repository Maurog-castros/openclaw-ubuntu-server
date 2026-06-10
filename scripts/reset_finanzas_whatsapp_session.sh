#!/usr/bin/env bash
# Resetea la sesión WhatsApp/Telegram del agente finanzas (estado failed / contexto inflado).
set -eu

REPO="${OPENCLAW_REPO:-/home/mauro/openclaw-mauro}"
SESSIONS_JSON="$REPO/data/config/agents/finanzas/sessions/sessions.json"
STAMP="$(date +%Y%m%d-%H%M%S)"

if [[ ! -f "$SESSIONS_JSON" ]]; then
  echo "No existe: $SESSIONS_JSON" >&2
  exit 1
fi

cp "$SESSIONS_JSON" "${SESSIONS_JSON}.bak-reset-${STAMP}"

python3 <<PY
import json
from pathlib import Path

path = Path("$SESSIONS_JSON")
data = json.loads(path.read_text(encoding="utf-8"))
keys = [
    "${FINANZAS_SESSION_KEY:-agent:fin:whatsapp:default:direct:+56945046845}",
    "agent:fin:main",
    "agent:finanzas:whatsapp:default:direct:+56945046845",
    "agent:finanzas:main",
]
stamp = "$STAMP"
repo = Path("$REPO")
bases = [
    repo / "data/config/agents/finanzas/sessions",
]
removed = []
for key in keys:
    entry = data.pop(key, None)
    if not entry:
        print(f"Sin entrada {key}; nada que resetear.")
        continue
    sid = entry.get("sessionId", "")
    removed.append((key, sid, entry.get("status")))
    print(f"Eliminada sesión {key} (status={entry.get('status')}, sessionId={sid})")
    if sid:
        for base in bases:
            for pattern in (f"{sid}.jsonl", f"{sid}.trajectory.jsonl", f"{sid}.trajectory-path.json"):
                jl = base / pattern
                if jl.exists():
                    bak = jl.with_name(jl.name + f".bak-reset-{stamp}")
                    jl.rename(bak)
                    print(f"Archivado: {bak}")
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Reset completado: {len(removed)} sesión(es)")
PY

echo "Listo. Envía /new o un mensaje nuevo por WhatsApp para abrir sesión limpia."
