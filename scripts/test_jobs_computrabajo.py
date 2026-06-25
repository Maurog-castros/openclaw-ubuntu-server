#!/usr/bin/env python3
from __future__ import annotations

import unittest

from jobs_computrabajo_scrape import job_id_from_url, merge_rows, parse_listing_page


SAMPLE_LISTING = """
<article class="box_offer outstanding" data-id='493212F04FC607BE61373E686DCF3405'>
    <h2 class="fs18 fwB prB">
        <a class="js-o-link fc_base" href="/ofertas-de-trabajo/oferta-de-trabajo-de-cloud-engineer-aws-kubernetes-493212F04FC607BE61373E686DCF3405">
            Cloud Engineer AWS Kubernetes
        </a>
    </h2>
    <p class="dFlex vm_fx fs16 fc_base mt5">
        <a class="fc_base t_ellipsis" href="https://cl.computrabajo.com/empresas/acme" offer-grid-article-company-url>
            ACME Cloud SpA
        </a>
    </p>
    <p class="fs16 fc_base mt5">
        <span class="mr10">
            Santiago - Providencia, R.Metropolitana
        </span>
    </p>
    <p class="fs13 fc_aux mt15">
        Hace 2 horas
    </p>
</article>
"""


class ComputrabajoScrapeTest(unittest.TestCase):
    def test_job_id_from_url(self):
        url = (
            "https://cl.computrabajo.com/ofertas-de-trabajo/"
            "oferta-de-trabajo-de-cloud-engineer-493212F04FC607BE61373E686DCF3405"
        )
        self.assertEqual(job_id_from_url(url), "493212F04FC607BE61373E686DCF3405")

    def test_parse_listing_page(self):
        cfg = {
            "core_skills": ["kubernetes", "aws", "devops", "terraform"],
            "target_roles": ["Cloud Engineer", "DevOps Engineer"],
            "demote_terms": [],
        }
        rows = parse_listing_page(SAMPLE_LISTING, "2026-06-23T12:00:00-04:00", "https://example.test", cfg)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "computrabajo")
        self.assertIn("Cloud Engineer", rows[0]["title"])
        self.assertGreaterEqual(int(rows[0]["match_score"]), 12)

    def test_merge_rows_dedup(self):
        a = [{"job_id": "A", "match_score": "20", "job_url": "https://a"}]
        b = [{"job_id": "A", "match_score": "10", "job_url": "https://a2"}, {"job_id": "B", "match_score": "15", "job_url": "https://b"}]
        merged = merge_rows(a, b, limit=10)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["job_id"], "A")


if __name__ == "__main__":
    unittest.main()
