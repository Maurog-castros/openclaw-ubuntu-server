#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path

os.environ["OPENCLAW_JOBS_DATA"] = tempfile.mkdtemp(prefix="openclaw-jobs-test-")

import jobs_ops
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


if __name__ == "__main__":
    unittest.main()
