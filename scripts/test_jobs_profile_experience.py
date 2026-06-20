#!/usr/bin/env python3
from __future__ import annotations
import unittest
from jobs_profile_experience import load_experiences


class JobsProfileExperienceTest(unittest.TestCase):
    def test_has_recent_roles(self):
        exps = load_experiences()
        companies = {str(e.get("company") or "") for e in exps}
        self.assertIn("HDI Seguros", companies)


if __name__ == "__main__":
    unittest.main()
