#!/usr/bin/env python3
from __future__ import annotations

import unittest

from jobs_perceptual_scrape import infer_workplace, parse_listing_page


SAMPLE_LISTING = """
<div class="awsm-job-listing-item awsm-list-item" id="awsm-list-item-5128527">
<div class="awsm-job-item">
<div class="awsm-list-left-col">
<h2 class="awsm-job-post-title">
<a href="https://laboral.perceptual.cl/empleos/desarrollador-backend-senior-typescript/">Desarrollador Backend Senior TypeScript</a>
</h2>
<div class="z-intro"><p>Empresa requiere Desarrollador Backend Senior TypeScript y NodeJs 20+.</p></div>
<div class="z-publish-date">Publicado: 24/06/2026</div>
</div>
<div class="awsm-list-right-col">
<div class="awsm-job-specification-item awsm-job-specification-job-location"><span class="awsm-job-specification-term">Huechuraba</span></div>
<div class="awsm-job-specification-item awsm-job-specification-job-type"><span class="awsm-job-specification-term">HIBRIDA</span></div>
<div class="awsm-job-specification-item awsm-job-specification-job-category"><span class="awsm-job-specification-term">Informática / Telecomunicaciones</span></div>
</div>
</div>
</div>
</div>
</div>
"""


class PerceptualScrapeTest(unittest.TestCase):
    def test_parse_listing_page(self):
        cfg = {
            "core_skills": ["typescript", "nodejs", "kubernetes", "aws"],
            "target_roles": ["DevOps Engineer", "Cloud Engineer"],
            "demote_terms": [],
        }
        rows = parse_listing_page(SAMPLE_LISTING, "2026-06-24T12:00:00-04:00", "https://example.test", cfg)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "perceptual")
        self.assertEqual(rows[0]["job_id"], "5128527")
        self.assertIn("Backend", rows[0]["title"])
        self.assertEqual(rows[0]["workplace"], "hybrid")

    def test_infer_workplace_remote(self):
        self.assertEqual(infer_workplace("Santiago", "trabajo remoto"), "remote")


if __name__ == "__main__":
    unittest.main()
