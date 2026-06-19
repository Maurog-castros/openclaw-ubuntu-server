#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path

os.environ["OPENCLAW_JOBS_DATA"] = tempfile.mkdtemp(prefix="openclaw-jobs-test-")

import jobs_ops
from jobs_common import load_config
from jobs_linkedin_recommended import job_id_from_url, normalize_rows
from jobs_registry_csv import append_application, csv_path, ensure_csv


class JobsOpsTest(unittest.TestCase):
    def test_evaluates_without_applying(self) -> None:
        data = jobs_ops.build_evaluation(
            "Senior DevOps Engineer empresa: Acme remoto Chile Kubernetes Terraform AWS observability"
        )

        self.assertIn(data["grade"], {"A", "B", "C", "D", "F"})
        self.assertIn(data["recommendation"], {"apply", "monitor", "skip"})
        self.assertIn(data["status"], {"evaluated", "skip"})
        self.assertEqual(data["company"], "Acme")

    def test_csv_header_migrates_old_tracker(self) -> None:
        path = csv_path({})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("applied_at,title,company,job_url,status,cv_file,match_score,questions_answered,notes\n", encoding="utf-8")

        ensure_csv(path)
        append_application(
            title="Senior SRE",
            company="Acme",
            job_url="https://example.com/job",
            status="evaluated",
            grade="B",
            recommendation="apply",
            report_file="/tmp/report.md",
        )

        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            self.assertIn("grade", reader.fieldnames or [])
            rows = list(reader)
        self.assertEqual(rows[-1]["grade"], "B")
        self.assertEqual(rows[-1]["recommendation"], "apply")

    def test_recommended_rows_are_deduped_and_scored(self) -> None:
        rows = normalize_rows(
            [
                {
                    "title": "Senior DevOps Engineer",
                    "company": "Acme",
                    "location": "Remoto Chile",
                    "job_url": "https://www.linkedin.com/jobs/view/4414362143/",
                    "collection_url": (
                        "https://www.linkedin.com/jobs/collections/recommended/"
                        "?currentJobId=4414362143&discover=recommended"
                    ),
                    "easy_apply": True,
                    "promoted": False,
                    "summary": "Kubernetes Terraform AWS observability remoto",
                },
                {
                    "title": "Duplicate",
                    "job_url": "https://www.linkedin.com/jobs/view/4414362143/",
                    "collection_url": "https://www.linkedin.com/jobs/view/4414362143/",
                },
            ],
            "2026-06-19T08:30:00-04:00",
            load_config(),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["job_id"], "4414362143")
        self.assertEqual(rows[0]["easy_apply"], "1")
        self.assertEqual(rows[0]["workplace"], "remote")
        self.assertGreater(int(rows[0]["match_score"]), 0)

    def test_job_id_from_recommended_url(self) -> None:
        self.assertEqual(
            job_id_from_url(
                "https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4414362143"
            ),
            "4414362143",
        )


if __name__ == "__main__":
    unittest.main()
