#!/usr/bin/env bash
# Limpia cola WhatsApp atascada (inbound.v1.pending) y sesión fin.
set -eu
REPO="${OPENCLAW_REPO:-/home/mauro/openclaw-mauro}"
DB="$REPO/data/config/state/openclaw.sqlite"
STAMP="$(date +%Y%m%d-%H%M%S)"

cp "$DB" "${DB}.bak-clear-pending-${STAMP}"

python3 <<PY
import json, sqlite3
from pathlib import Path

db = Path("$DB")
con = sqlite3.connect(db)
cur = con.cursor()
cur.execute("DELETE FROM plugin_state_entries WHERE plugin_id='whatsapp' AND namespace LIKE 'inbound.v1.pending%'")
print(f"pending deleted: {cur.rowcount}")
cur.execute(
    "DELETE FROM delivery_queue_entries WHERE status='failed' "
    "AND (session_key LIKE 'agent:fin%' OR session_key LIKE 'agent:finanzas%')"
)
print(f"failed delivery deleted (fin): {cur.rowcount}")
con.commit()
con.close()
PY

bash "$REPO/scripts/reset_finanzas_whatsapp_session.sh"

cd "$REPO/openclaw"
docker compose -f docker-compose.yml -f docker-compose.finanzas-mounts.yml restart openclaw-gateway
echo "Cola limpia. Envía UN mensaje de texto por WhatsApp."
