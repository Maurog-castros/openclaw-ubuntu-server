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
 def test_sparse_keyword_match_never_reaches_threshold(self):
  result=score_cv("AWS Kubernetes Python","Se requiere AWS Kubernetes Python")
  self.assertLess(result["score"],9.5)
if __name__=="__main__":unittest.main()
