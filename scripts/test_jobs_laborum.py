#!/usr/bin/env python3
"""Focused tests for CV-to-Laborum profile generation."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from jobs_laborum_profile import build_profile, newest_cv  # noqa: E402


class LaborumProfileTest(unittest.TestCase):
    def test_latest_cv_experiences_are_structured(self) -> None:
        profile = build_profile(newest_cv())
        experiences = profile["experiences"]

        self.assertEqual(8, profile["experience_count"])
        self.assertEqual("HDI Seguros Chile", experiences[0]["company"])
        self.assertEqual((10, 2024), (experiences[0]["start_month"], experiences[0]["start_year"]))
        self.assertEqual((12, 2025), (experiences[0]["end_month"], experiences[0]["end_year"]))
        self.assertEqual("Quintec", experiences[-1]["company"])
        self.assertTrue(all(len(item["description"]) <= 1000 for item in experiences))
        self.assertTrue(all(item["people_managed"] == 0 for item in experiences))
        self.assertTrue(all(item["managed_budget"] is False for item in experiences))
        self.assertEqual(len(experiences), len({item["key"] for item in experiences}))

    def test_apply_requires_confirmation_token(self) -> None:
        proc = subprocess.run(
            [
                str(ROOT / ".venv-jobs-portals/bin/python"),
                str(SCRIPTS / "jobs_laborum_sync.py"),
                "--apply",
                "--json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual("error", payload["status"])
        self.assertIn("UPDATE-LABORUM", payload["whatsapp_reply"])


if __name__ == "__main__":
    unittest.main()
