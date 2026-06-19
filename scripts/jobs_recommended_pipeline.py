#!/usr/bin/env python3
"""Enriquece recommended, rankea CVs y prepara aprobacion."""
from __future__ import annotations
import argparse, csv, json, time
from datetime import datetime
from jobs_common import JOBS_WS, load_config
from jobs_cv_rank import generate_adapted_cv, rank_cvs, write_ranking_csv
from jobs_linkedin_browser import ensure_login, launch_browser, new_context
VACANCIES_DIR=JOBS_WS/"vacancies"
DETAIL_JS=r"""() => {const t=s=>(document.querySelector(s)?.innerText||'').replace(/\s+/g,' ').trim();return {title:t('.job-details-jobs-unified-top-card__job-title')||t('h1'),company:t('.job-details-jobs-unified-top-card__company-name'),location:t('.job-details-jobs-unified-top-card__primary-description-container'),description:t('.jobs-description__content')||t('.jobs-box__html-content')||t('#job-details')||t('[class*="jobs-description"]'),body:(document.body.innerText||'')}}"""
def rows():
 p=JOBS_WS/"linkedin_recommended_latest.csv"
 with p.open(encoding="utf-8",newline="") as h:return list(csv.DictReader(h))
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
 if len(desc)<120:
  shot=d/"extraction-error.png";page.screenshot(path=str(shot),full_page=True);raise RuntimeError(f"JD incompleta ({len(desc)}); screenshot={shot}")
 return {"title":str(data.get("title") or row.get("title") or ""),"company":str(data.get("company") or row.get("company") or ""),"location":str(data.get("location") or row.get("location") or ""),"description":desc}
def vacancy_score(data,row):
 cfg,text=load_config()," ".join(data.values()).lower()
 r=sum(x.lower() in text for x in cfg.get("target_roles",[]));s=sum(x.lower() in text for x in cfg.get("core_skills",[]));d=sum(x.lower() in text for x in cfg.get("demote_terms",[]))
 loc=1.5 if any(x in text for x in ("remote","remoto","híbrido","hibrido","chile","latam")) else .5
 return round(max(0,min(10,min(3,r*1.5)+min(4,s*.4)+loc+(1 if row.get("easy_apply")=="1" else .5)+.5-d)),2)
def process(page,row,threshold):
 jid=row.get("job_id") or row["job_url"].rstrip("/").split("/")[-1];d=VACANCIES_DIR/jid;d.mkdir(parents=True,exist_ok=True);prev=old(d);data=extract(page,row,d)
 (d/"description.txt").write_text(data["description"]+"\n",encoding="utf-8");ranks=rank_cvs(data["description"]);ranking=write_ranking_csv(ranks,d,"cv");best=float(ranks[0].get("score") or 0) if ranks else 0
 generated=str(generate_adapted_cv(data["description"],d,f"{jid}-adapted")) if best<threshold else ""
 state={"job_id":jid,"discovered_at":row.get("scraped_at"),"analyzed_at":datetime.now().astimezone().isoformat(timespec="seconds"),**data,"workplace":row.get("workplace"),"easy_apply":row.get("easy_apply")=="1","job_url":row.get("job_url"),"vacancy_score":vacancy_score(data,row),"best_cv":ranks[0] if ranks else {},"best_cv_score":best,"generated_cv":generated,"ranking_csv":str(ranking),"decision_status":prev.get("decision_status") or "pending_approval","decision_at":prev.get("decision_at") or "","applied_at":prev.get("applied_at") or ""}
 report=d/"analysis.md";report.write_text(f"# {state['title']}\n\nEmpresa: {state['company']}\nJob ID: {jid}\nURL: {state['job_url']}\nNota vacante: {state['vacancy_score']}/10\nMejor CV: {state['best_cv'].get('file','')} ({best}/10)\nCV adaptado: {generated or 'no requerido'}\nEstado: {state['decision_status']}\n\nAprobar: /jobs aprobar {jid}\nDescartar: /jobs descartar {jid}\nPostular: /jobs postular {jid}\n\n## JD\n\n{data['description']}\n",encoding="utf-8");state["analysis_report"]=str(report)
 (d/"job.json").write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return state
def save_summary(states):
 states.sort(key=lambda x:float(x.get("vacancy_score") or 0),reverse=True);p=JOBS_WS/f"ranked_vacancies_{datetime.now():%Y-%m-%d}.csv";f=["job_id","vacancy_score","title","company","location","workplace","easy_apply","best_cv_score","best_cv_file","generated_cv","decision_status","job_url"]
 with p.open("w",encoding="utf-8",newline="") as h:
  w=csv.DictWriter(h,fieldnames=f);w.writeheader()
  for s in states:w.writerow({**{k:s.get(k,"") for k in f},"best_cv_file":s.get("best_cv",{}).get("file","")})
 (JOBS_WS/"ranked_vacancies_latest.csv").write_text(p.read_text(encoding="utf-8"),encoding="utf-8");return p
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--limit",type=int,default=20);ap.add_argument("--threshold",type=float,default=9.5);ap.add_argument("--headed",action="store_true");ap.add_argument("--json",action="store_true");a=ap.parse_args();states=[];errors=[]
 from playwright.sync_api import sync_playwright
 with sync_playwright() as p:
  browser=launch_browser(p,headless=not a.headed);context=new_context(browser);page=context.new_page()
  try:
   ensure_login(page)
   for row in rows()[:a.limit]:
    try:states.append(process(page,row,a.threshold))
    except Exception as exc:errors.append({"job_id":row.get("job_id",""),"error":str(exc)[:500]})
  finally:context.close();browser.close()
 ranked=save_summary(states);payload={"status":"ok" if not errors else "partial","agent":"jobs","processed":len(states),"errors":errors,"ranked_csv":str(ranked),"vacancies_dir":str(VACANCIES_DIR),"jobs":states,"whatsapp_reply":f"Jobs analizados: {len(states)}; errores: {len(errors)}; ranking: {ranked}"}
 (JOBS_WS/"recommended_pipeline_latest.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(json.dumps(payload,ensure_ascii=False,indent=2) if a.json else payload["whatsapp_reply"])
if __name__=="__main__":main()
