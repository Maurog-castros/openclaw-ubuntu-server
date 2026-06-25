#!/usr/bin/env python3
from __future__ import annotations
import json,os,tempfile,unittest
from pathlib import Path
os.environ["OPENCLAW_JOBS_DATA"]=tempfile.mkdtemp(prefix="jobs-pipeline-test-")
import jobs_approval
from jobs_cv_rank import score_cv
class JobsPipelineTest(unittest.TestCase):
 def setUp(self):
  self.job_id="4414362143";d=jobs_approval.VACANCIES/self.job_id;d.mkdir(parents=True,exist_ok=True)
  (d/"job.json").write_text(json.dumps({"job_id":self.job_id,"title":"Cloud Engineer","decision_status":"pending_approval"}),encoding="utf-8")
 def test_apply_requires_approval(self):
  with self.assertRaises(PermissionError):jobs_approval.require_approved(self.job_id)
  jobs_approval.set_decision(self.job_id,"aprobar")
  self.assertEqual(jobs_approval.require_approved(self.job_id)["decision_status"],"approved")
 def test_discard_blocks_apply(self):
  jobs_approval.set_decision(self.job_id,"descartar")
  with self.assertRaises(PermissionError):jobs_approval.require_approved(self.job_id)
 def test_approve_all_from_latest_report(self):
  import csv
  ranked=jobs_approval.JOBS_WS/"ranked_vacancies_latest.csv"
  ranked.parent.mkdir(parents=True,exist_ok=True)
  jid2="3856264";d=jobs_approval.VACANCIES/jid2;d.mkdir(parents=True,exist_ok=True)
  (d/"job.json").write_text(json.dumps({"job_id":jid2,"title":"Cloud Engineer AWS","decision_status":"pending_approval","vacancy_score":7.1}),encoding="utf-8")
  with ranked.open("w",encoding="utf-8",newline="") as h:
   w=csv.DictWriter(h,fieldnames=["job_id","vacancy_score","title","company","availability_status","decision_status"])
   w.writeheader();w.writerow({"job_id":self.job_id,"vacancy_score":"8","title":"Cloud Engineer","company":"ACME","availability_status":"open","decision_status":"pending_approval"})
   w.writerow({"job_id":jid2,"vacancy_score":"7.1","title":"Cloud Engineer AWS","company":"RyC","availability_status":"open","decision_status":"pending_approval"})
  bulk=jobs_approval.approve_all_from_latest_report()
  self.assertEqual(2,len(bulk["approved"]))
  self.assertIn("2 aprobadas",bulk["whatsapp_reply"])
 def test_sparse_keyword_match_never_reaches_threshold(self):
  result=score_cv("AWS Kubernetes Python","Se requiere AWS Kubernetes Python")
  self.assertLess(result["score"],9.5)
if __name__=="__main__":unittest.main()
