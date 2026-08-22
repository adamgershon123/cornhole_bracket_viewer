import sqlite3
import unittest

from event_analytics_jobs import (
    FROZEN_PREDICTION,
    TOURNAMENT_GRADES,
    enqueue_event_analytics_job,
    event_analytics_job_status,
)
from lifecycle_runner import initialize_lifecycle_schema, monitor_event


class EventAnalyticsJobTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("CREATE TABLE events(event_id INTEGER PRIMARY KEY, status TEXT, bracket_completed INTEGER DEFAULT 0)")

    def tearDown(self):
        self.conn.close()

    def test_monitor_persists_independent_automation_choices(self):
        initialize_lifecycle_schema(self.conn)
        monitor_event(
            self.conn, event_id=123, schedule_format="BRACKET",
            source_timezone="America/New_York", auto_freeze_prediction=True,
            auto_grade_on_complete=False,
        )
        row = self.conn.execute("SELECT * FROM monitored_events WHERE event_id='123'").fetchone()
        self.assertEqual(row["auto_freeze_prediction"], 1)
        self.assertEqual(row["auto_grade_on_complete"], 0)

    def test_jobs_are_durable_and_idempotent_while_active(self):
        first = enqueue_event_analytics_job(self.conn, 123, FROZEN_PREDICTION, "TEST")
        second = enqueue_event_analytics_job(self.conn, 123, FROZEN_PREDICTION, "TEST")
        enqueue_event_analytics_job(self.conn, 123, TOURNAMENT_GRADES, "TEST")
        self.assertEqual(first["requested_at"], second["requested_at"])
        self.assertEqual(len(event_analytics_job_status(self.conn, 123)), 2)


if __name__ == "__main__":
    unittest.main()
