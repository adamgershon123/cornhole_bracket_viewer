import sqlite3
import unittest

from lifecycle_runner import auto_monitor_discovered_events, classify_no_activity_events


class LifecycleAutoMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE discovered_events(
                event_id INTEGER PRIMARY KEY,
                event_date TEXT,
                advertised_time TEXT,
                status TEXT,
                format_candidate TEXT,
                location_lat REAL,
                location_lng REAL
            )
            """
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_enrolls_nearby_swap_and_swiss_without_assuming_timezone(self) -> None:
        self.conn.executemany(
            "INSERT INTO discovered_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (101, "2026-07-26", "6:00 PM", "A", "SWAP_CANDIDATE", 26.7, -80.0),
                (102, "2026-07-27", "7:00 PM", "A", "SWISS_CANDIDATE", 34.9, -81.0),
                (103, "2026-07-27", "8:00 PM", "A", "BRACKET_CANDIDATE", 34.9, -81.0),
            ],
        )
        result = auto_monitor_discovered_events(
            self.conn,
            as_of="2026-07-26T12:00:00+00:00",
        )
        rows = self.conn.execute(
            "SELECT event_id, schedule_format, source_timezone, poll_start_at FROM monitored_events ORDER BY event_id"
        ).fetchall()
        self.assertEqual(result["added"], 2)
        self.assertEqual(
            [(row["event_id"], row["schedule_format"], row["source_timezone"]) for row in rows],
            [("101", "SWAP", "America/New_York"), ("102", "SWISS", "America/New_York")],
        )

    def test_excludes_completed_and_out_of_window_events(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE monitored_events(
                event_id TEXT PRIMARY KEY,
                schedule_format TEXT NOT NULL,
                source_timezone TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                added_at TEXT NOT NULL,
                last_polled_at TEXT,
                last_poll_status TEXT,
                last_poll_message TEXT,
                poll_start_at TEXT
            )
            """
        )
        self.conn.execute(
            "INSERT INTO monitored_events(event_id, schedule_format, enabled, added_at) VALUES ('201', 'SWAP', 1, 'x')"
        )
        self.conn.executemany(
            "INSERT INTO discovered_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (201, "2026-07-26", "6:00 PM", "C", "SWAP_CANDIDATE", 26.7, -80.0),
                (202, "2026-08-01", "7:00 PM", "A", "SWAP_CANDIDATE", 26.7, -80.0),
            ],
        )
        result = auto_monitor_discovered_events(
            self.conn,
            as_of="2026-07-26T12:00:00+00:00",
        )
        self.assertEqual(result["eligible"], 0)
        self.assertEqual(result["completedDisabled"], 1)
        self.assertEqual(
            self.conn.execute("SELECT enabled FROM monitored_events WHERE event_id='201'").fetchone()[0],
            0,
        )

    def test_classifies_expired_event_without_competitive_data(self) -> None:
        for statement in (
            "CREATE TABLE upcoming_matchup_candidates(event_id TEXT, home_player_ids_json TEXT, away_player_ids_json TEXT)",
            "CREATE TABLE matches(event_id INTEGER)",
            "CREATE TABLE player_rounds(event_id INTEGER)",
            "CREATE TABLE swap_standings(event_id INTEGER)",
            "CREATE TABLE event_results(event_id INTEGER)",
            "CREATE TABLE team_members(event_id INTEGER)",
            "CREATE TABLE bracket_prediction_snapshots(event_id INTEGER)",
            "CREATE TABLE shadow_prediction_runs(event_id TEXT)",
        ):
            self.conn.execute(statement)
        self.conn.execute(
            "INSERT INTO discovered_events VALUES (301, '2026-07-25', '6:00 PM', 'A', 'SWAP_CANDIDATE', 26.7, -80.0)"
        )
        auto_monitor_discovered_events(
            self.conn,
            as_of="2026-07-25T12:00:00+00:00",
        )
        self.assertEqual(classify_no_activity_events(self.conn, as_of_date="2026-07-26"), 1)
        row = self.conn.execute(
            "SELECT enabled, last_poll_status, last_poll_message FROM monitored_events WHERE event_id='301'"
        ).fetchone()
        self.assertEqual(row["enabled"], 0)
        self.assertEqual(row["last_poll_status"], "NO_ACTIVITY")
        self.assertIn("No roster", row["last_poll_message"])


if __name__ == "__main__":
    unittest.main()
