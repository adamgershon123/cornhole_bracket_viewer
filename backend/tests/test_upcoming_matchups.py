from __future__ import annotations

import sqlite3
import unittest

from season_platform import init_db
from upcoming_matchups import (
    create_due_shadow_predictions,
    ingest_schedule_matchups,
    matchup_discovery_report,
)


def schedule_row(
    match_id: int,
    start: str | None,
    *,
    status: int = 1,
    home: list[int] | None = None,
    away: list[int] | None = None,
) -> dict:
    return {
        "matchID": match_id,
        "matchStatusID": status,
        "matchStartTime": start,
        "homeTeam": [{"playerID": value} for value in ([1] if home is None else home)],
        "awayTeam": [{"playerID": value} for value in ([2] if away is None else away)],
    }


class UpcomingMatchupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def add_history(self, player_id: int, points: int) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO events(event_id, event_date) VALUES (1, '2026-07-01')"
        )
        for round_no in range(1, 21):
            self.conn.execute(
                """
                INSERT INTO player_rounds(
                    event_id, match_id, game_id, round_no, player_id, team_id,
                    gross_points, opponent_points, net_points, scored_points,
                    bags_in, bags_on, bags_off, four_bagger, round_result,
                    event_date, match_type, bracket_type
                ) VALUES (1, '1', 1, ?, ?, ?, ?, 7, ?, ?, ?, 0, ?, 0, ?,
                          '2026-07-01', 'D', 'W')
                """,
                (
                    round_no,
                    player_id,
                    f"1:{player_id}",
                    points,
                    points - 7,
                    max(points - 7, 0),
                    min(points // 3, 4),
                    4 - min(points // 3, 4),
                    "W" if points > 7 else "L",
                ),
            )
        self.conn.commit()

    def test_schedule_ingestion_classifies_ready_and_blocked_rows(self) -> None:
        payload = {
            "data": {
                "overAllSchedule": [
                    schedule_row(1, "2026-07-25T14:00:00"),
                    schedule_row(2, None),
                    schedule_row(3, "2026-07-25T15:00:00", status=5),
                    schedule_row(4, "2026-07-25T16:00:00", away=[]),
                ]
            }
        }
        result = ingest_schedule_matchups(
            self.conn,
            event_id=50,
            payload=payload,
            source_endpoint="swiss-pairing-schedule-breakdown",
            format_name="SWISS",
            source_timezone="America/New_York",
        )
        self.assertEqual(result["rowsSeen"], 4)
        self.assertEqual(result["ready"], 1)
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["missingTime"], 1)
        self.assertEqual(result["missingSides"], 1)
        report = matchup_discovery_report(self.conn)
        self.assertEqual(report["totalCandidates"], 4)

    def test_naive_timestamp_without_timezone_is_blocked(self) -> None:
        result = ingest_schedule_matchups(
            self.conn,
            event_id=50,
            payload={"data": {"overAllSchedule": [
                schedule_row(1, "2026-07-25T14:00:00")
            ]}},
            source_endpoint="swiss-pairing-schedule-breakdown",
            format_name="SWISS",
        )
        self.assertEqual(result["missingTime"], 1)
        row = self.conn.execute(
            "SELECT discovery_issue FROM upcoming_matchup_candidates"
        ).fetchone()
        self.assertEqual(row["discovery_issue"], "MISSING_SOURCE_TIMEZONE")

    def test_due_candidates_create_one_shadow_run(self) -> None:
        self.add_history(1, 9)
        self.add_history(2, 6)
        ingest_schedule_matchups(
            self.conn,
            event_id=50,
            payload={"data": {"overAllSchedule": [
                schedule_row(7, "2026-07-25T14:00:00+00:00")
            ]}},
            source_endpoint="swiss-pairing-schedule-breakdown",
            format_name="SWISS",
        )
        first = create_due_shadow_predictions(
            self.conn,
            as_of="2026-07-25T13:00:00+00:00",
            lookahead_minutes=120,
        )
        second = create_due_shadow_predictions(
            self.conn,
            as_of="2026-07-25T13:30:00+00:00",
            lookahead_minutes=120,
        )
        self.assertEqual(first["predicted"], 1)
        self.assertEqual(second["alreadyRecorded"], 1)
        count = self.conn.execute(
            "SELECT COUNT(*) FROM shadow_prediction_runs"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_roster_reveal_after_event_start_can_freeze_verified_pregame_prediction(self) -> None:
        self.add_history(1, 9)
        self.add_history(2, 6)
        row = schedule_row(8, None)
        row.update({
            "matchStatus": "Scheduled",
            "homeScore": 0,
            "awayScore": 0,
            "gameResults": {"homeScore": 0, "awayScore": 0},
            "resultGameStatus": None,
            "matchEndTime": None,
        })
        ingestion = ingest_schedule_matchups(
            self.conn,
            event_id=51,
            payload={"data": {"schedule": [row]}},
            source_endpoint="swap-schedule-all",
            format_name="SWAP",
            source_timezone="America/New_York",
            event_start_at="2026-07-25T22:00:00+00:00",
            observed_at="2026-07-25T22:17:00+00:00",
        )
        result = create_due_shadow_predictions(
            self.conn,
            as_of="2026-07-25T22:17:00+00:00",
            lookahead_minutes=1440,
        )
        stored = self.conn.execute(
            "SELECT timing_basis, recorded_at, scheduled_start_at FROM shadow_prediction_runs"
        ).fetchone()
        self.assertEqual(ingestion["ready"], 1)
        self.assertEqual(result["predicted"], 1)
        self.assertEqual(stored["timing_basis"], "EVENT_START_ROSTER_REVEAL")
        self.assertGreater(stored["recorded_at"], stored["scheduled_start_at"])

    def test_nonzero_score_is_not_verified_as_pregame(self) -> None:
        row = schedule_row(9, None, status=2)
        row.update({
            "matchStatus": "In Progress",
            "homeScore": 1,
            "awayScore": 0,
            "gameResults": {"homeScore": 1, "awayScore": 0},
        })
        ingest_schedule_matchups(
            self.conn,
            event_id=52,
            payload={"data": {"schedule": [row]}},
            source_endpoint="swap-schedule-all",
            format_name="SWAP",
            source_timezone="America/New_York",
            event_start_at="2026-07-25T22:00:00+00:00",
            observed_at="2026-07-25T22:17:00+00:00",
        )
        candidate = self.conn.execute(
            "SELECT discovery_status, pregame_verified FROM upcoming_matchup_candidates"
        ).fetchone()
        self.assertEqual(candidate["discovery_status"], "BLOCKED")
        self.assertEqual(candidate["pregame_verified"], 0)


if __name__ == "__main__":
    unittest.main()
