from __future__ import annotations

import sqlite3
import unittest

from baseline_predictions import score_matchup
from round_loss_recent_challenger import MODEL_VERSION as CHALLENGER_MODEL_VERSION
from season_platform import init_db
from shadow_predictions import (
    create_shadow_prediction,
    initialize_shadow_schema,
    record_shadow_outcome,
    shadow_performance_report,
)
from stage_a_features import build_matchup_features


class ShadowPredictionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        init_db(self.conn)
        initialize_shadow_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def add_history(self, player_id: int, points: int, rounds: int = 20) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO events(event_id, event_date) VALUES (1, '2026-07-01')"
        )
        for round_no in range(1, rounds + 1):
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

    def test_shadow_prediction_is_pregame_and_idempotent(self) -> None:
        self.add_history(1, 9)
        self.add_history(2, 6)
        first = create_shadow_prediction(
            self.conn,
            event_id=10,
            match_id=5,
            side_a_player_ids=[1],
            side_b_player_ids=[2],
            recorded_at="2026-07-10T12:00:00+00:00",
            scheduled_start_at="2026-07-10T13:00:00+00:00",
        )
        second = create_shadow_prediction(
            self.conn,
            event_id=10,
            match_id=5,
            side_a_player_ids=[1],
            side_b_player_ids=[2],
            recorded_at="2026-07-10T12:30:00+00:00",
            scheduled_start_at="2026-07-10T13:00:00+00:00",
        )
        self.assertEqual(first["status"], "PREDICTED")
        self.assertEqual(first["shadowRunId"], second["shadow_run_id"])
        count = self.conn.execute(
            "SELECT COUNT(*) FROM shadow_prediction_runs"
        ).fetchone()[0]
        self.assertEqual(count, 1)
        challenger_count = self.conn.execute(
            "SELECT COUNT(*) FROM shadow_challenger_predictions"
        ).fetchone()[0]
        self.assertEqual(challenger_count, 1)
        self.assertEqual(first["challenger"]["status"], "PREDICTED")

    def test_prediction_after_start_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            create_shadow_prediction(
                self.conn,
                event_id=10,
                match_id=5,
                side_a_player_ids=[1],
                side_b_player_ids=[2],
                recorded_at="2026-07-10T14:00:00+00:00",
                scheduled_start_at="2026-07-10T13:00:00+00:00",
            )

    def test_outcomes_score_prediction_and_report_coverage(self) -> None:
        self.add_history(1, 9)
        self.add_history(2, 6)
        predicted = create_shadow_prediction(
            self.conn,
            event_id=10,
            match_id=5,
            side_a_player_ids=[1],
            side_b_player_ids=[2],
            recorded_at="2026-07-10T12:00:00+00:00",
            scheduled_start_at="2026-07-10T13:00:00+00:00",
        )
        create_shadow_prediction(
            self.conn,
            event_id=10,
            match_id=6,
            side_a_player_ids=[1],
            side_b_player_ids=[999],
            recorded_at="2026-07-10T12:00:00+00:00",
            scheduled_start_at="2026-07-10T13:00:00+00:00",
        )
        record_shadow_outcome(
            self.conn,
            shadow_run_id=predicted["shadowRunId"],
            side_a_won=True,
            source="ACL_MATCH_RESULT",
            resolved_at="2026-07-10T14:00:00+00:00",
        )
        report = shadow_performance_report(self.conn)
        self.assertEqual(report["totalRuns"], 2)
        self.assertEqual(report["coverageRate"], 0.5)
        self.assertEqual(report["resolvedPredictions"], 1)
        self.assertEqual(report["accuracy"], 1.0)
        self.assertEqual(sum(report["abstentionReasons"].values()), 1)
        self.assertEqual(report["commonSample"]["resolvedPredictions"], 1)
        self.assertEqual(
            report["models"][CHALLENGER_MODEL_VERSION]["resolvedPredictions"],
            1,
        )

    def test_candidate_confidence_is_capped(self) -> None:
        self.add_history(1, 12, rounds=100)
        self.add_history(2, 1, rounds=100)
        matchup = build_matchup_features(
            self.conn,
            side_a_player_ids=[1],
            side_b_player_ids=[2],
            cutoff_at="2026-07-10T00:00:00+00:00",
        )
        prediction = score_matchup(
            matchup,
            model_version="fitted-ppr-logistic-v1",
        )
        self.assertLessEqual(prediction["sideAProbability"], 0.85)
        self.assertGreaterEqual(prediction["sideAProbability"], 0.15)


if __name__ == "__main__":
    unittest.main()
