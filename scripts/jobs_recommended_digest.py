#!/usr/bin/env python3
"""Digest WhatsApp de vacantes analizadas pendientes."""
from __future__ import annotations
import argparse,csv,json
from jobs_common import JOBS_WS
from jobs_daily_auto import resolve_target_file,send_whatsapp
def build():
 p=JOBS_WS/"ranked_vacancies_latest.csv"
 if not p.exists():raise FileNotFoundError(f"Falta {p}")
 with p.open(encoding="utf-8",newline="") as h:rows=list(csv.DictReader(h))
 rows=[r for r in rows if r.get("availability_status")=="open"]
 pending=[r for r in rows if r.get("decision_status")=="pending_approval"]
 lines=[f"Jobs recomendados: {len(rows)} vacantes abiertas verificadas / {len(pending)} pendientes",""]
 for r in pending[:8]:
  lines += [f"{r['job_id']} | {r.get('vacancy_score')}/10 | {r.get('title')} @ {r.get('company')}",f"CV {r.get('best_cv_score')}/10: {r.get('best_cv_file')}",f"{r.get('job_url')}","Aprobar: /jobs aprobar "+r["job_id"],""]
 lines.append(f"Ranking: {p}");return "\n".join(lines),rows
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--send-whatsapp",action="store_true");ap.add_argument("--json",action="store_true");a=ap.parse_args()
 try:
  msg,rows=build();sent={"ok":False,"reason":"not requested"}
  if a.send_whatsapp:
   target=resolve_target_file()
   if not target:raise FileNotFoundError("Falta whatsapp_allow_from.txt")
   sent=send_whatsapp(msg,target)
  payload={"status":"ok" if not a.send_whatsapp or sent.get("ok") else "partial","agent":"jobs","count":len(rows),"sent":sent,"whatsapp_reply":msg}
 except Exception as exc:payload={"status":"error","agent":"jobs","whatsapp_reply":f"Jobs digest: {exc}"}
 print(json.dumps(payload,ensure_ascii=False,indent=2) if a.json else payload["whatsapp_reply"])
if __name__=="__main__":main()
