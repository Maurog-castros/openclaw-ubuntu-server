#!/usr/bin/env python3
"""Pruebas sync Google Sheets Jobs."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jobs_google_sheet_setup import FS, dashboard_rows
from jobs_google_sheet_sync import modalidad_from_job, portal_from_url, row_from_job, sheet_status


class JobsGoogleSheetSyncTest(unittest.TestCase):
    def test_portal_and_status(self) -> None:
        self.assertEqual("linkedin", portal_from_url("https://www.linkedin.com/jobs/view/1"))
        self.assertEqual("chiletrabajos", portal_from_url("https://www.chiletrabajos.cl/trabajo/x-1"))
        self.assertEqual("pendiente_aprobacion", sheet_status({"decision_status": "pending_approval"}))
        self.assertEqual("postulada", sheet_status({"applied_at": "2026-06-20T10:00:00-04:00"}))

    def test_row_shape(self) -> None:
        row = row_from_job({
            "job_id": "123",
            "title": "DevOps",
            "company": "ACME",
            "job_url": "https://www.linkedin.com/jobs/view/123",
            "location": "Santiago (Hibrido)",
            "workplace": "hybrid",
            "discovered_at": "2026-06-20T08:00:00-04:00",
            "analyzed_at": "2026-06-20T09:00:00-04:00",
            "vacancy_score": 8.1,
            "best_cv": {"file": "CV_DevOps.docx", "score": 9.0},
            "best_cv_score": 9.0,
            "generated_cv": "/tmp/CV_123-adapted.docx",
            "decision_status": "pending_approval",
        })
        self.assertEqual(32, len(row))
        self.assertEqual("123", row[0])
        self.assertEqual("linkedin", row[1])
        self.assertEqual("hibrido", modalidad_from_job({"workplace": "hybrid", "location": "Santiago (Hibrido)"}))
        self.assertEqual("pendiente_aprobacion", row[13])

    def test_formulas_use_locale_separator(self) -> None:
        formulas = [
            cell["userEnteredValue"]["formulaValue"]
            for row in dashboard_rows()
            for cell in row["values"]
            if "formulaValue" in cell.get("userEnteredValue", {})
        ]
        self.assertTrue(any("COUNTIF(" in formula for formula in formulas))
        self.assertTrue(all(FS in formula for formula in formulas if "COUNTIF" in formula))

    def test_load_vacancies_from_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_dir = root / "vacancies" / "999"
            job_dir.mkdir(parents=True)
            (job_dir / "job.json").write_text(json.dumps({
                "job_id": "999",
                "title": "SRE",
                "company": "Test",
                "job_url": "https://example.com/999",
                "vacancy_score": 7.5,
                "decision_status": "pending_approval",
            }), encoding="utf-8")
            with patch("jobs_google_sheet_sync.VACANCIES", root / "vacancies"):
                from jobs_google_sheet_sync import load_vacancies

                jobs = load_vacancies()
            self.assertEqual(1, len(jobs))
            self.assertEqual("999", jobs[0]["job_id"])


if __name__ == "__main__":
    unittest.main()
