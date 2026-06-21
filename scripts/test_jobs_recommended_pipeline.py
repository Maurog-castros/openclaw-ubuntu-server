#!/usr/bin/env python3
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from jobs_recommended_pipeline import source_row_is_fresh, vacancy_availability


class JobsRecommendedPipelineTest(unittest.TestCase):
    def test_rejects_expired_chiletrabajos_vacancy(self):
        status, reason = vacancy_availability(
            "Este anuncio ha expirado o ha sido desactivado por el empleador."
        )
        self.assertEqual(status, "closed")
        self.assertIn("expirado", reason)

    def test_rejects_linkedin_no_longer_accepting(self):
        status, reason = vacancy_availability(
            "This job is no longer accepting applications"
        )
        self.assertEqual(status, "closed")
        self.assertIn("no longer accepting applications", reason)

    def test_accepts_live_detail_without_closed_markers(self):
        status, reason = vacancy_availability(
            "Postula ahora. Buscamos Site Reliability Engineer para nuestro equipo."
        )
        self.assertEqual(status, "open")
        self.assertIn("live detail page", reason)

    def test_accepts_recent_source_row(self):
        now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
        row = {"scraped_at": (now - timedelta(hours=2)).isoformat()}
        self.assertTrue(source_row_is_fresh(row, now=now))

    def test_rejects_stale_source_row(self):
        now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
        row = {"scraped_at": (now - timedelta(hours=48)).isoformat()}
        self.assertFalse(source_row_is_fresh(row, now=now))

    def test_rejects_missing_or_invalid_source_timestamp(self):
        now = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(source_row_is_fresh({}, now=now))
        self.assertFalse(source_row_is_fresh({"scraped_at": "invalid"}, now=now))


if __name__ == "__main__":
    unittest.main()
