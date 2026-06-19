#!/usr/bin/env bash
set -euo pipefail
REPO="${OPENCLAW_REPO:-/home/mauro/Dev/openclaw-mauro}"
SCRAPE="${JOBS_RECOMMENDED_SCRAPE_SCHEDULE:-30 8 * * *} cd $REPO && bash scripts/run-jobs-recommended-daily.sh # openclaw-jobs-recommended-scrape"
ANALYZE="${JOBS_RECOMMENDED_ANALYZE_SCHEDULE:-40 8 * * *} cd $REPO && bash scripts/run-jobs-recommended-analysis.sh # openclaw-jobs-recommended-analysis"
REPORT="${JOBS_RECOMMENDED_REPORT_SCHEDULE:-50 8 * * *} cd $REPO && bash scripts/run-jobs-recommended-report.sh # openclaw-jobs-recommended-report"
current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "$current" | grep -v 'openclaw-jobs-recommended' | grep -v 'run-jobs-recommended-' || true)"
printf '%s\n%s\n%s\n%s\n' "$filtered" "$SCRAPE" "$ANALYZE" "$REPORT" | sed '/^$/d' | crontab -
echo "Cron Jobs recommended instalado:"
crontab -l | grep 'openclaw-jobs-recommended'
