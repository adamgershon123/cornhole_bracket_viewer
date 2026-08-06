from __future__ import annotations

import json
import sqlite3
import unittest
from unittest.mock import patch

from outcome_ingestion import (
    experimental_performance_report,
    ingest_completed_outcomes,
)
from season_platform import fetch_and_index_upcoming_schedule, init_db


class OutcomeIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def add_experiment(self, match_id: str, home_probability: float) -> None:
        self.conn.execute(
            """
            INSERT INTO inplay_experimental_predictions(
                event_id, match_id, model_label, observed_at,
                observation_status, home_player_ids_json,
                away_player_ids_json, home_acl_ppr, away_acl_ppr,
                home_win_probability, away_win_probability, limitations_json
            ) VALUES ('10', ?, 'test', '2026-01-01T12:00:00+00:00',
                      'IN_PROGRESS', '[]', '[]', 6, 6, ?, ?, '[]')
            """,
            (match_id, home_probability, 1 - home_probability),
        )
        self.conn.commit()

    def test_completed_schedule_resolves_experimental_predictions(self) -> None:
        self.add_experiment("1", 0.48)
        self.add_experiment("2", 0.18)
        payload = {
            "status": "OK",
            "data": [
                {
                    "matchID": 1,
                    "matchStatusID": 5,
                    "matchStatus": "Completed",
                    "homeScore": 22,
                    "awayScore": 19,
                },
                {
                    "matchID": 2,
                    "matchStatusID": 5,
                    "matchStatus": "Completed",
                    "homeScore": 12,
                    "awayScore": 22,
                },
            ],
        }
        result = ingest_completed_outcomes(
            self.conn,
            event_id=10,
            payload=payload,
            source_endpoint="swap-schedule-all",
            resolved_at="2026-01-01T14:00:00+00:00",
        )
        self.assertEqual(result["outcomesStored"], 2)
        self.assertEqual(result["experimentalResolved"], 2)
        outcomes = self.conn.execute(
            """
            SELECT match_id, outcome_home_won
            FROM inplay_experimental_predictions
            ORDER BY match_id
            """
        ).fetchall()
        self.assertEqual(
            [(row["match_id"], row["outcome_home_won"]) for row in outcomes],
            [("1", 1), ("2", 0)],
        )
        report = experimental_performance_report(self.conn)
        self.assertEqual(
            report["confidenceBuckets"]["COIN_FLIP_50_55"]["accuracy"],
            0.0,
        )
        self.assertEqual(
            report["confidenceBuckets"]["HIGH_CONFIDENCE_70_PLUS"]["accuracy"],
            1.0,
        )

    def test_incomplete_rows_are_not_outcomes(self) -> None:
        result = ingest_completed_outcomes(
            self.conn,
            event_id=10,
            payload={"data": [{
                "matchID": 1,
                "matchStatusID": 1,
                "homeScore": 0,
                "awayScore": 0,
            }]},
            source_endpoint="swap-schedule-all",
        )
        self.assertEqual(result["outcomesStored"], 0)

    @patch("season_platform.create_due_shadow_predictions")
    @patch("season_platform.ingest_schedule_matchups")
    @patch("season_platform.cached_get")
    def test_swiss_schedule_poll_resolves_completed_predictions(
        self,
        cached_get,
        ingest_schedule_matchups,
        create_due_shadow_predictions,
    ) -> None:
        self.add_experiment("49", 0.335)
        cached_get.return_value = ({
            "status": "OK",
            "data": {
                "completedMatchList": [{
                    "matchID": 49,
                    "matchStatusID": 5,
                    "matchStatus": "Completed",
                    "homeScore": 14,
                    "awayScore": 21,
                }],
            },
        }, {"source": "network", "sourcePayloadId": None})
        ingest_schedule_matchups.return_value = {"indexed": 1}
        create_due_shadow_predictions.return_value = {"predicted": 0}

        result = fetch_and_index_upcoming_schedule(
            self.conn,
            event_id=10,
            schedule_format="SWISS",
            source_timezone="America/New_York",
        )

        self.assertEqual(result["outcomes"]["outcomesStored"], 1)
        row = self.conn.execute(
            "SELECT outcome_home_won FROM inplay_experimental_predictions "
            "WHERE event_id='10' AND match_id='49'"
        ).fetchone()
        self.assertEqual(row["outcome_home_won"], 0)


if __name__ == "__main__":
    unittest.main()
