#!/usr/bin/env python3
from __future__ import annotations
import unittest
from jobs_chiletrabajos_scrape import (
    fetch_job_detail,
    is_login_redirect,
    is_recommended_dashboard,
    job_id_from_url,
    merge_rows,
    parse_listing_page,
    parse_recommended_page,
    parse_rss,
    recommended_page_html,
    scrape_listings,
)
from jobs_profile_experience import load_experiences


SAMPLE_LISTING = """
<div class="job-item with-thumb">
    <div class="col-sm-12 px-0">
        <h2 class="title overflow-hidden">
            <a href="https://www.chiletrabajos.cl/trabajo/ingeniero-a-sre-ssr-nivel-ingles-avanzado-3823795" class="font-weight-bold">Ingeniero/a SRE Ssr</a>
        </h2>
        <h3 class="meta">Haibu Solutions Spa,<a href="https://www.chiletrabajos.cl/ciudad/santiago.html">Santiago</a></h3>
        <h3 class="meta"><a href='https://www.chiletrabajos.cl/trabajo/ingeniero-a-sre-ssr-nivel-ingles-avanzado-3823795'><i class="far fa-calendar"></i> 19 de Junio de 2026</a></h3>
    </div>
    <div class="col-sm-12 px-0 mt-2">
        <p class="description">Buscamos SRE con AWS, Kubernetes, Terraform y CI/CD en entornos cloud.</p>
    </div>
</div>
"""


class ChileTrabajosScrapeTest(unittest.TestCase):
    def test_job_id_from_url(self):
        self.assertEqual(job_id_from_url("https://www.chiletrabajos.cl/trabajo/foo-3823795"), "3823795")

    def test_parse_listing_page(self):
        rows = parse_listing_page(SAMPLE_LISTING, "2026-06-19T12:00:00-04:00", "https://example.test", {"core_skills": ["kubernetes", "aws"], "target_roles": ["SRE"], "demote_terms": []})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["job_id"], "3823795")
        self.assertIn("SRE", rows[0]["title"])
        self.assertGreaterEqual(int(rows[0]["match_score"]), 12)

    def test_fetch_job_detail_live(self):
        data = fetch_job_detail("https://www.chiletrabajos.cl/trabajo/ingeniero-a-sre-ssr-nivel-ingles-avanzado-3823795")
        self.assertGreater(len(data.get("description") or ""), 120)
        self.assertIn("SRE", data.get("title", "") + data.get("description", ""))

    def test_load_credentials_from_env(self):
        from jobs_chiletrabajos_browser import load_chiletrabajos_credentials, storage_state_path

        creds = load_chiletrabajos_credentials()
        self.assertIsNotNone(creds, "Se esperan credenciales en runtime/secrets/.env")
        email, password = creds
        self.assertIn("@", email)
        self.assertGreater(len(password), 3)
        self.assertTrue(str(storage_state_path()).endswith("chiletrabajos_storage_state.json"))

    def test_save_session_requires_login(self):
        from jobs_chiletrabajos_browser import save_session

        class FakePage:
            url = "https://www.chiletrabajos.cl/chtlogin"

            def content(self):
                return "Usuario y/o contraseña incorrectos"

            def inner_text(self, _sel):
                return "Ingresa a tu cuenta"

            def locator(self, _sel):
                class Loc:
                    def count(self):
                        return 1

                    def first(self):
                        return self

                    def is_visible(self):
                        return True

                return Loc()

        with self.assertRaises(RuntimeError):
            save_session(FakePage())

    def test_scrape_listings_filters_by_score(self):
        rows = scrape_listings(pages=1, category_slug="informatica", min_score=50, limit=5)
        self.assertEqual(rows, [])

    def test_is_login_redirect(self):
        self.assertTrue(is_login_redirect("<form id='username'>", "https://www.chiletrabajos.cl/chtlogin"))
        self.assertFalse(
            is_recommended_dashboard(
                "<form id='username'>Ingresa a Chiletrabajos",
                "https://www.chiletrabajos.cl/chtlogin",
            )
        )
        self.assertTrue(
            is_recommended_dashboard(
                "<h1>Ofertas recomendadas</h1><div class='job-item'>",
                "https://www.chiletrabajos.cl/dashboard/ofertas-recomendadas",
            )
        )

    def test_parse_recommended_page_bonus_and_promoted(self):
        cfg = {"core_skills": ["kubernetes", "aws"], "target_roles": ["SRE"], "demote_terms": []}
        html = (
            "<h2>Ofertas recomendadas</h2>"
            + SAMPLE_LISTING
            + "<h2>Ofertas destacadas</h2><div class='job-item'>otro</div>"
        )
        section = recommended_page_html(html)
        self.assertNotIn("destacadas", section.lower())
        rows = parse_recommended_page(
            html,
            "2026-06-19T12:00:00-04:00",
            "https://www.chiletrabajos.cl/dashboard/ofertas-recomendadas",
            cfg,
            score_bonus=4,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["promoted"], "1")
        self.assertGreaterEqual(int(rows[0]["match_score"]), 16)

    def test_parse_rss_sample(self):
        sample = """
        <item><title>DevOps AWS | Santiago</title><link>https://www.chiletrabajos.cl/trabajo/devops-aws-1234567</link>
        <description>Ingeniero DevOps AWS Kubernetes Terraform CI/CD</description><guid>1234567</guid></item>
        """
        cfg = {"core_skills": ["kubernetes", "aws", "devops", "terraform"], "target_roles": ["DevOps Engineer"], "demote_terms": []}
        rows = parse_rss(sample, "2026-06-19T12:00:00-04:00", "https://example/rss", cfg)
        self.assertEqual(len(rows), 1)
        self.assertGreaterEqual(int(rows[0]["match_score"]), 12)

    def test_load_experiences(self):
        exps = load_experiences()
        self.assertGreaterEqual(len(exps), 3)
        self.assertTrue(any("HDI" in str(e.get("company")) for e in exps))


if __name__ == "__main__":
    unittest.main()
