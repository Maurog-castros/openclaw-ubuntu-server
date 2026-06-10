#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/home/mauro/openclaw-mauro"
DATE="$(date +%F)"
TS="$(date +%F_%H%M%S)"
CLI_CONTAINER="openclaw-openclaw-cli-1"

REPORTS_DIR="$BASE_DIR/reports/intelligence"
CONTENT_DIR="$BASE_DIR/content/drafts"
CRM_DIR="$BASE_DIR/crm"
LOGS_DIR="$BASE_DIR/logs"

mkdir -p "$REPORTS_DIR" "$CONTENT_DIR" "$CRM_DIR" "$LOGS_DIR"

INTEL_OUT="$REPORTS_DIR/${DATE}-report.md"
CONTENT_OUT="$CONTENT_DIR/${DATE}-linkedin-draft.md"
SALES_OUT="$CRM_DIR/${DATE}-opportunities.md"
CONSOLIDATED_OUT="$REPORTS_DIR/${DATE}-consolidated-report.md"
LOG_FILE="$LOGS_DIR/marketing-daily-${TS}.log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "[$(date -Is)] Starting marketing daily run"

docker exec "$CLI_CONTAINER" openclaw agent --local \
  --agent intel \
  --session-key "agent:intel:daily:${DATE}" \
  --message "Genera el Daily Intelligence Report de hoy para Chile con: Strong Trends, Technical Pain Points, Viral Topics, Potential Clients, Product Opportunities, Recommended Content. Incluye fuentes URL reales." \
  --json > "$INTEL_OUT.json"

python3 - <<"PY2" "$INTEL_OUT.json" "$INTEL_OUT"
import json,sys
j=json.load(open(sys.argv[1],encoding="utf-8"))
text=""
for p in j.get("payloads",[]):
    if p.get("text"):
        text=p["text"]
        break
open(sys.argv[2],"w",encoding="utf-8").write(text.strip()+"\n")
PY2

docker exec "$CLI_CONTAINER" openclaw agent --local \
  --agent content \
  --session-key "agent:content:daily:${DATE}" \
  --message "Crea 1 borrador de post LinkedIn basado en el reporte de inteligencia de hoy. Estructura obligatoria: Hook, Core Insight, Practical Example, Technical Lesson, Business Impact, CTA." \
  --json > "$CONTENT_OUT.json"

python3 - <<"PY2" "$CONTENT_OUT.json" "$CONTENT_OUT"
import json,sys
j=json.load(open(sys.argv[1],encoding="utf-8"))
text=""
for p in j.get("payloads",[]):
    if p.get("text"):
        text=p["text"]
        break
open(sys.argv[2],"w",encoding="utf-8").write(text.strip()+"\n")
PY2

docker exec "$CLI_CONTAINER" openclaw agent --local \
  --agent sales \
  --session-key "agent:sales:daily:${DATE}" \
  --message "Genera recomendaciones CRM del día con: company, contact role, signal, source, conversation status, next action. Además incluye 2 mensajes de outreach personalizados sin spam." \
  --json > "$SALES_OUT.json"

python3 - <<"PY2" "$SALES_OUT.json" "$SALES_OUT"
import json,sys
j=json.load(open(sys.argv[1],encoding="utf-8"))
text=""
for p in j.get("payloads",[]):
    if p.get("text"):
        text=p["text"]
        break
open(sys.argv[2],"w",encoding="utf-8").write(text.strip()+"\n")
PY2

cat > "$CONSOLIDATED_OUT" <<EOR
# Consolidated Marketing Daily Report - ${DATE}

## Intelligence
- Source file: ${INTEL_OUT}

## Content Draft
- Source file: ${CONTENT_OUT}

## Sales/CRM Opportunities
- Source file: ${SALES_OUT}

## Execution Log
- ${LOG_FILE}
EOR

echo "[$(date -Is)] Completed marketing daily run"
echo "Generated files:"
echo "- $INTEL_OUT"
echo "- $CONTENT_OUT"
echo "- $SALES_OUT"
echo "- $CONSOLIDATED_OUT"
