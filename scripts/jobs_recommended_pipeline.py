#!/usr/bin/env python3
"""Enriquece recommended, rankea CVs y prepara aprobacion."""
from __future__ import annotations
import argparse, csv, json, time
from datetime import datetime, timedelta
from jobs_common import JOBS_WS, ensure_gateway_writable, load_config
from jobs_cv_rank import generate_adapted_cv, rank_cvs, write_ranking_csv
from jobs_linkedin_browser import ensure_login, launch_browser, new_context
VACANCIES_DIR=JOBS_WS/"vacancies"
DETAIL_JS=r"""() => {const t=s=>(document.querySelector(s)?.innerText||'').replace(/\s+/g,' ').trim();return {title:t('.job-details-jobs-unified-top-card__job-title')||t('h1'),company:t('.job-details-jobs-unified-top-card__company-name'),location:t('.job-details-jobs-unified-top-card__primary-description-container'),description:t('.jobs-description__content')||t('.jobs-box__html-content')||t('#job-details')||t('[class*="jobs-description"]'),body:(document.body.innerText||'')}}"""
MAX_SOURCE_AGE_HOURS=36
CLOSED_MARKERS=(
 "este anuncio ha expirado",
 "ha sido desactivado por el empleador",
 "anuncio expirado",
 "oferta expirada",
 "vacante cerrada",
 "oferta cerrada",
 "ya no acepta solicitudes",
 "ya no se aceptan solicitudes",
 "no longer accepting applications",
 "this job is no longer available",
 "job is no longer available",
 "oferta ha finalizado",
 "oferta finalizada",
 "ya no esta disponible",
 "ya no está disponible",
 "aviso finalizado",
)
class ClosedVacancyError(RuntimeError):pass
def source_row_is_fresh(row,now=None,max_age_hours=MAX_SOURCE_AGE_HOURS):
 raw=str(row.get("scraped_at") or "").strip()
 if not raw:return False
 try:stamp=datetime.fromisoformat(raw.replace("Z","+00:00"))
 except ValueError:return False
 current=now or datetime.now().astimezone()
 if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=current.tzinfo)
 return current-timedelta(hours=max_age_hours)<=stamp<=current+timedelta(minutes=5)
def vacancy_availability(*texts):
 blob=" ".join(str(text or "") for text in texts).lower()
 for marker in CLOSED_MARKERS:
  if marker in blob:return "closed",marker
 return "open","live detail page without closed markers"
def rows(now=None):
 out=[]
 for name in ("linkedin_recommended_latest.csv","chiletrabajos_latest.csv","computrabajo_latest.csv","perceptual_latest.csv"):
  p=JOBS_WS/name
  if not p.exists(): continue
  with p.open(encoding="utf-8",newline="") as h:
   for row in csv.DictReader(h):
    if row.get("job_url") and source_row_is_fresh(row,now=now):out.append(row)
 seen=set();dedup=[]
 for row in out:
  key=row.get("job_id") or row.get("job_url")
  if key in seen: continue
  seen.add(key);dedup.append(row)
 dedup.sort(key=lambda row:int(row.get("match_score") or 0),reverse=True)
 return dedup
def extract_chiletrabajos(row,d):
 from jobs_chiletrabajos_scrape import fetch_job_detail
 data=fetch_job_detail(row["job_url"])
 status,reason=vacancy_availability(data.get("description"),data.get("title"))
 if status!="open":raise ClosedVacancyError(f"Vacante cerrada: {reason}; url={row['job_url']}")
 data.update(availability_status="open",availability_reason=reason)
 if len(str(data.get("description") or ""))<120:
  shot=d/"extraction-error.png"
  raise RuntimeError(f"JD incompleta ChileTrabajos ({len(data.get('description') or '')}); url={row['job_url']}")
 return data
def extract_computrabajo(row,d):
 from jobs_computrabajo_scrape import fetch_job_detail
 data=fetch_job_detail(row["job_url"])
 status,reason=vacancy_availability(data.get("description"),data.get("title"))
 if status!="open":raise ClosedVacancyError(f"Vacante cerrada: {reason}; url={row['job_url']}")
 data.update(availability_status="open",availability_reason=reason)
 if len(str(data.get("description") or ""))<120:
  raise RuntimeError(f"JD incompleta Computrabajo ({len(data.get('description') or '')}); url={row['job_url']}")
 return data
def extract_perceptual(row,d):
 from jobs_perceptual_scrape import fetch_job_detail
 data=fetch_job_detail(row["job_url"])
 status,reason=vacancy_availability(data.get("description"),data.get("title"))
 if status!="open":raise ClosedVacancyError(f"Vacante cerrada: {reason}; url={row['job_url']}")
 data.update(availability_status="open",availability_reason=reason)
 if len(str(data.get("description") or ""))<120:
  raise RuntimeError(f"JD incompleta Perceptual ({len(data.get('description') or '')}); url={row['job_url']}")
 return data
def old(d):
 try:return json.loads((d/"job.json").read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError):return {}
def extract(page,row,d):
 page.goto(row["job_url"],wait_until="domcontentloaded",timeout=90000);time.sleep(3)
 for label in ("Ver más","Show more"):
  try:
   b=page.get_by_role("button",name=label).first
   if b.count() and b.is_visible():b.click(timeout=3000)
  except Exception:pass
 data=dict(page.evaluate(DETAIL_JS));desc=str(data.get("description") or "").strip()
 if len(desc)<120:
  body=str(data.get("body") or "")
  for marker in ("Acerca del empleo", "About the job"):
   if marker in body: desc=body.split(marker,1)[1];break
  for end in ("Configurar alerta", "Ver empleos similares", "Empleos similares", "Personas también"):
   if end in desc: desc=desc.split(end,1)[0]
  desc=desc.strip()
 for end in ("… más","Establecer una alerta","Configurar alerta","Ver empleos similares","Empleos similares","Personas también"):
  if end in desc: desc=desc.split(end,1)[0]
 desc=desc.strip()
 status,reason=vacancy_availability(data.get("body"),desc)
 if status!="open":raise ClosedVacancyError(f"Vacante cerrada: {reason}; url={row['job_url']}")
 if len(desc)<120:
  shot=d/"extraction-error.png";page.screenshot(path=str(shot),full_page=True);raise RuntimeError(f"JD incompleta ({len(desc)}); screenshot={shot}")
 return {"title":str(data.get("title") or row.get("title") or ""),"company":str(data.get("company") or row.get("company") or ""),"location":str(data.get("location") or row.get("location") or ""),"description":desc,"availability_status":"open","availability_reason":reason}
def vacancy_score(data,row):
 cfg,text=load_config()," ".join(data.values()).lower()
 r=sum(x.lower() in text for x in cfg.get("target_roles",[]));s=sum(x.lower() in text for x in cfg.get("core_skills",[]));d=sum(x.lower() in text for x in cfg.get("demote_terms",[]))
 loc=1.5 if any(x in text for x in ("remote","remoto","híbrido","hibrido","chile","latam")) else .5
 return round(max(0,min(10,min(3,r*1.5)+min(4,s*.4)+loc+(1 if row.get("easy_apply")=="1" else .5)+.5-d)),2)
def process(page,row,threshold):
 jid=row.get("job_id") or row["job_url"].rstrip("/").split("/")[-1];d=VACANCIES_DIR/jid;d.mkdir(parents=True,exist_ok=True);prev=old(d)
 if "chiletrabajos.cl" in str(row.get("job_url") or ""): data=extract_chiletrabajos(row,d)
 elif "computrabajo.com" in str(row.get("job_url") or ""): data=extract_computrabajo(row,d)
 elif "perceptual.cl" in str(row.get("job_url") or ""): data=extract_perceptual(row,d)
 else: data=extract(page,row,d)
 (d/"description.txt").write_text(data["description"]+"\n",encoding="utf-8");ranks=rank_cvs(data["description"]);ranking=write_ranking_csv(ranks,d,"cv");best=float(ranks[0].get("score") or 0) if ranks else 0
 generated=str(generate_adapted_cv(data["description"],d,f"{jid}-adapted")) if best<threshold else ""
 state={"job_id":jid,"discovered_at":row.get("scraped_at"),"analyzed_at":datetime.now().astimezone().isoformat(timespec="seconds"),"availability_checked_at":datetime.now().astimezone().isoformat(timespec="seconds"),**data,"workplace":row.get("workplace"),"easy_apply":row.get("easy_apply")=="1","job_url":row.get("job_url"),"vacancy_score":vacancy_score(data,row),"best_cv":ranks[0] if ranks else {},"best_cv_score":best,"generated_cv":generated,"ranking_csv":str(ranking),"decision_status":prev.get("decision_status") or "pending_approval","decision_at":prev.get("decision_at") or "","applied_at":prev.get("applied_at") or ""}
 report=d/"analysis.md";report.write_text(f"# {state['title']}\n\nEmpresa: {state['company']}\nJob ID: {jid}\nURL: {state['job_url']}\nNota vacante: {state['vacancy_score']}/10\nMejor CV: {state['best_cv'].get('file','')} ({best}/10)\nCV adaptado: {generated or 'no requerido'}\nEstado: {state['decision_status']}\n\nAprobar: /jobs aprobar {jid}\nDescartar: /jobs descartar {jid}\nPostular: /jobs postular {jid}\n\n## JD\n\n{data['description']}\n",encoding="utf-8");state["analysis_report"]=str(report)
 (d/"job.json").write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");ensure_gateway_writable(d);ensure_gateway_writable(d/"job.json");return state
def save_summary(states):
 states=[s for s in states if s.get("availability_status")=="open"];states.sort(key=lambda x:float(x.get("vacancy_score") or 0),reverse=True);p=JOBS_WS/f"ranked_vacancies_{datetime.now():%Y-%m-%d}.csv";f=["job_id","vacancy_score","title","company","location","workplace","easy_apply","best_cv_score","best_cv_file","generated_cv","decision_status","availability_status","availability_checked_at","job_url"]
 with p.open("w",encoding="utf-8",newline="") as h:
  w=csv.DictWriter(h,fieldnames=f);w.writeheader()
  for s in states:w.writerow({**{k:s.get(k,"") for k in f},"best_cv_file":s.get("best_cv",{}).get("file","")})
 (JOBS_WS/"ranked_vacancies_latest.csv").write_text(p.read_text(encoding="utf-8"),encoding="utf-8");return p
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--limit",type=int,default=20);ap.add_argument("--threshold",type=float,default=9.5);ap.add_argument("--headed",action="store_true");ap.add_argument("--json",action="store_true");a=ap.parse_args();states=[];errors=[]
 closed=[];input_rows=rows()
 from playwright.sync_api import sync_playwright
 with sync_playwright() as p:
  browser=launch_browser(p,headless=not a.headed);context=new_context(browser);page=context.new_page()
  try:
   pending=[r for r in input_rows[:a.limit] if "linkedin.com" in str(r.get("job_url") or "")]
   if pending:
    ensure_login(page)
   for row in input_rows[:a.limit]:
    try:states.append(process(page,row,a.threshold))
    except ClosedVacancyError as exc:closed.append({"job_id":row.get("job_id",""),"reason":str(exc)[:500]})
    except Exception as exc:errors.append({"job_id":row.get("job_id",""),"error":str(exc)[:500]})
  finally:context.close();browser.close()
 ranked=save_summary(states);payload={"status":"ok" if not errors else "partial","agent":"jobs","input_rows":len(input_rows),"processed":len(states),"closed_excluded":closed,"errors":errors,"ranked_csv":str(ranked),"vacancies_dir":str(VACANCIES_DIR),"jobs":states,"whatsapp_reply":f"Jobs abiertos verificados: {len(states)}; cerrados excluidos: {len(closed)}; errores: {len(errors)}; ranking: {ranked}"}
 (JOBS_WS/"recommended_pipeline_latest.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(json.dumps(payload,ensure_ascii=False,indent=2) if a.json else payload["whatsapp_reply"])
if __name__=="__main__":main()
