#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from jobs_recommended_on_demand import ProgressNotifier, progress_percent


class JobsRecommendedOnDemandTest(unittest.TestCase):
    def test_progress_stays_inside_stage(self):
        self.assertEqual(progress_percent(35, 95, 0, 150), 36)
        self.assertLess(progress_percent(35, 95, 999, 150), 95)
        self.assertGreater(progress_percent(35, 95, 75, 150), 35)

    @patch("jobs_recommended_on_demand.start_notification")
    def test_notifier_bounds_active_sends(self, start_notification):
        active = Mock()
        active.poll.return_value = None
        start_notification.return_value = active
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.txt"
            target.write_text("+56911111111\n", encoding="utf-8")
            notifier = ProgressNotifier(target)
            notifier.offer("Jobs 25% — buscando")
            notifier.offer("Jobs 30% — buscando")
        self.assertEqual(start_notification.call_count, 1)
        self.assertEqual(notifier.pending, "Jobs 30% — buscando")


if __name__ == "__main__":
    unittest.main()
