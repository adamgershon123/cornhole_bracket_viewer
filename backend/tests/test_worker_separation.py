from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class WorkerSeparationTests(unittest.TestCase):
    def test_collection_entrypoint_only_starts_collection(self) -> None:
        source = (ROOT / "backend" / "collection_worker.py").read_text(encoding="utf-8")
        self.assertIn("start_historical_backfill_worker()", source)
        self.assertNotIn("start_automated_discovery_worker", source)
        self.assertNotIn("run_event_analytics_job_cycle", source)

    def test_operations_entrypoint_owns_user_requested_jobs(self) -> None:
        source = (ROOT / "backend" / "operations_worker.py").read_text(encoding="utf-8")
        self.assertIn("start_prediction_lifecycle_worker()", source)
        self.assertIn("run_event_analytics_job_cycle", source)
        self.assertNotIn("start_historical_backfill_worker", source)

    def test_analytics_entrypoint_is_lower_priority_only(self) -> None:
        source = (ROOT / "backend" / "analytics_worker.py").read_text(encoding="utf-8")
        self.assertIn("start_automated_discovery_worker", source)
        self.assertNotIn("start_historical_backfill_worker", source)
        self.assertNotIn("run_event_analytics_job_cycle", source)

    def test_cloud_compose_defines_three_independent_workers(self) -> None:
        source = (ROOT / "docker-compose.cloud.yml").read_text(encoding="utf-8")
        self.assertIn("collection-worker:", source)
        self.assertIn("operations-worker:", source)
        self.assertIn("analytics-worker:", source)
        self.assertNotIn("\n  workers:\n", source)


if __name__ == "__main__":
    unittest.main()
