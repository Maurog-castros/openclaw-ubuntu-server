#!/usr/bin/env python3
"""Aprobacion humana durable para vacantes Jobs."""
from __future__ import annotations
import argparse,csv,json
from datetime import datetime
from pathlib import Path
from typing import Any
from jobs_common import JOBS_WS, ensure_gateway_writable
VACANCIES=JOBS_WS/"vacancies"
VALID={"approve":"approved","aprobar":"approved","discard":"discarded","descartar":"discarded"}
def state_path(job_id:str)->Path:return VACANCIES/job_id/"job.json"
def load_job(job_id:str)->dict[str,Any]:
 p=state_path(job_id)
 if not p.exists():raise FileNotFoundError(f"Vacante {job_id} no analizada.")
 return json.loads(p.read_text(encoding="utf-8"))
def save_job(job:dict[str,Any])->None:
 p=state_path(str(job["job_id"]));p.write_text(json.dumps(job,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");ensure_gateway_writable(p);ensure_gateway_writable(p.parent)
def set_decision(job_id:str,action:str)->dict[str,Any]:
 job=load_job(job_id);status=VALID[action];job["decision_status"]=status;job["decision_at"]=datetime.now().astimezone().isoformat(timespec="seconds");save_job(job);return job
def require_approved(job_id:str)->dict[str,Any]:
 job=load_job(job_id)
 if job.get("decision_status")!="approved":raise PermissionError(f"Vacante {job_id} no aprobada; estado={job.get('decision_status')}. Usa /jobs aprobar {job_id}.")
 return job
def pending()->list[dict[str,Any]]:
 out=[]
 for p in sorted(VACANCIES.glob("*/job.json")):
  try:
   j=json.loads(p.read_text(encoding="utf-8"))
   if j.get("decision_status")=="pending_approval":out.append(j)
  except json.JSONDecodeError:pass
 return sorted(out,key=lambda j:float(j.get("vacancy_score") or 0),reverse=True)
def latest_report_pending()->list[dict[str,str]]:
 p=JOBS_WS/"ranked_vacancies_latest.csv"
 if not p.exists():raise FileNotFoundError(f"Falta ultimo reporte ({p}). Usa /jobs reporte ahora.")
 with p.open(encoding="utf-8",newline="") as h:rows=list(csv.DictReader(h))
 out=[]
 for r in rows:
  if r.get("availability_status")!="open" or r.get("decision_status")!="pending_approval":continue
  jid=str(r.get("job_id") or "")
  if not jid:continue
  try:
   job=load_job(jid)
   if job.get("decision_status")!="pending_approval":continue
  except FileNotFoundError:continue
  out.append(r)
 return out
def approve_all_from_latest_report()->dict[str,Any]:
 rows=latest_report_pending()
 if not rows:return {"approved":[],"errors":[],"whatsapp_reply":"Jobs: no hay vacantes pendientes en el ultimo reporte."}
 approved=[];errors=[]
 for r in rows:
  jid=str(r["job_id"])
  try:approved.append(set_decision(jid,"aprobar"))
  except Exception as exc:errors.append({"job_id":jid,"error":str(exc)})
 lines=[f"Jobs: {len(approved)} aprobadas del ultimo reporte ({len(rows)} pendientes)",""]
 for j in approved[:10]:lines.append(f"{j['job_id']} | {j.get('vacancy_score')}/10 | {j.get('title','')}")
 if len(approved)>10:lines.append(f"... y {len(approved)-10} mas")
 if errors:lines.append("");lines.append(f"Errores ({len(errors)}):");lines.extend(f"{e['job_id']}: {e['error']}" for e in errors[:5])
 return {"approved":approved,"errors":errors,"whatsapp_reply":"\n".join(lines)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument("action",choices=[*VALID,"status","estado"]);ap.add_argument("job_id",nargs="?",default="");ap.add_argument("--reporte",action="store_true");ap.add_argument("--json",action="store_true");a=ap.parse_args()
 try:
  if a.action in VALID:
   if a.reporte:
    if a.action!="aprobar":raise ValueError("Bulk reporte solo soporta aprobar. Usa /jobs aprobar todos.")
    bulk=approve_all_from_latest_report();msg=bulk["whatsapp_reply"];job={"approved":bulk["approved"],"errors":bulk["errors"]}
   elif not a.job_id:raise ValueError("Falta job_id")
   else:
    job=set_decision(a.job_id,a.action);msg=f"Jobs: {job['job_id']} {job['decision_status']} - {job.get('title','')}"
  elif a.job_id:
   job=load_job(a.job_id);msg=f"Jobs: {job['job_id']} {job.get('decision_status')} | {job.get('vacancy_score')}/10 | {job.get('title')}"
  else:
   jobs=pending();msg="Jobs pendientes:\n"+"\n".join(f"{j['job_id']} | {j.get('vacancy_score')}/10 | {j.get('title')}" for j in jobs[:10]);job={"pending":jobs}
  payload={"status":"ok","agent":"jobs","job":job,"whatsapp_reply":msg}
 except Exception as exc:payload={"status":"error","agent":"jobs","whatsapp_reply":f"Jobs decision: {exc}"}
 print(json.dumps(payload,ensure_ascii=False,indent=2) if a.json else payload["whatsapp_reply"])
if __name__=="__main__":main()
