#!/usr/bin/env python3
from __future__ import annotations

import unittest
from unittest.mock import patch

import jobs_delegate


class JobsDelegateOnDemandTest(unittest.TestCase):
    def test_command_phrases(self):
        for text in ("reporte ahora", "reporte manual", "buscar ahora", "buscar vacantes ahora"):
            self.assertIsNotNone(jobs_delegate.ON_DEMAND_REPORT_RE.search(text), text)

    def test_decision_job_id_accepts_chiletrabajos_linkedin_and_computrabajo(self):
        for jid in ("3856264", "4428952059", "3832196", "8DEDB29FDCEC91A161373E686DCF3405", "5128527"):
            self.assertIsNotNone(jobs_delegate.JOB_ID_RE.search(f"aprobar {jid}"), jid)

    def test_perceptual_phrases(self):
        for text in ("perceptual", "laboral.perceptual"):
            self.assertIsNotNone(jobs_delegate.PERCEPTUAL_RE.search(text), text)

    def test_approve_report_phrases(self):
        for text in ("aprobar todos", "aprobar reporte", "aprobar ultimo reporte"):
            self.assertIsNotNone(jobs_delegate.APPROVE_REPORT_RE.search(text), text)

    def test_computrabajo_login_phrases(self):
        for text in ("computrabajo login", "login computrabajo"):
            self.assertIsNotNone(jobs_delegate.COMPUTRABAJO_LOGIN_RE.search(text), text)

    @patch("jobs_delegate.run_json")
    def test_runs_full_pipeline_and_public_fallback(self, run_json):
        run_json.side_effect = [
            (0, {"status": "ok"}, "", ""),
            (1, {"status": "error"}, "", "login expired"),
            (0, {"status": "ok"}, "", ""),
            (0, {"status": "ok"}, "", ""),
            (0, {"status": "ok"}, "", ""),
            (0, {"processed": 8, "closed_excluded": [{}, {}], "errors": []}, "", ""),
            (0, {"count": 8, "whatsapp_reply": "8 abiertas"}, "", ""),
        ]

        payload = jobs_delegate.run_recommended_on_demand({"TEST": "1"})

        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["on_demand"])
        self.assertEqual(payload["pipeline"]["processed"], 8)
        self.assertEqual(payload["pipeline"]["closed_excluded"], 2)
        self.assertEqual(payload["whatsapp_reply"], "8 abiertas")
        self.assertIn("--no-session", run_json.call_args_list[2].args[0])
        self.assertEqual(run_json.call_count, 7)

    @patch("jobs_delegate.subprocess.Popen")
    def test_starts_background_worker(self, popen):
        popen.return_value.pid = 4321

        payload = jobs_delegate.start_recommended_on_demand({"TEST": "1"})

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["pid"], 4321)
        self.assertIn("cada 5 segundos", payload["whatsapp_reply"])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])


if __name__ == "__main__":
    unittest.main()
