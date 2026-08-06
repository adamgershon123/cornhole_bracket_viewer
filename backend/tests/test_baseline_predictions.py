from __future__ import annotations

import sqlite3
import unittest

from baseline_predictions import (
    create_prediction,
    initialize_prediction_schema,
    score_matchup,
)
from season_platform import init_db
from stage_a_features import build_matchup_features


class BaselinePredictionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        init_db(self.conn)
        initialize_prediction_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def add_history(self, player_id: int, rounds: int, points: int) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO events(event_id, event_date) VALUES (1, '2026-07-01')"
        )
        for round_no in range(1, rounds + 1):
            game_no = (round_no - 1) // 10 + 1
            self.conn.execute(
                """
                INSERT INTO player_rounds(
                    event_id, match_id, game_id, round_no, player_id, team_id,
                    gross_points, opponent_points, net_points, scored_points,
                    bags_in, bags_on, bags_off, four_bagger, round_result,
                    event_date, match_type, bracket_type
                ) VALUES (1, ?, ?, ?, ?, ?, ?, 7, ?, ?, ?, ?, ?, ?, ?,
                          '2026-07-01', 'D', 'W')
                """,
                (
                    str(game_no),
                    game_no,
                    round_no,
                    player_id,
                    f"1:{player_id}",
                    points,
                    points - 7,
                    max(points - 7, 0),
                    min(points // 3, 4),
                    0,
                    4 - min(points // 3, 4),
                    1 if points == 12 else 0,
                    "W" if points > 7 else "L" if points < 7 else "T",
                ),
            )
        self.conn.commit()

    def matchup(self, side_a: int, side_b: int) -> dict:
        return build_matchup_features(
            self.conn,
            side_a_player_ids=[side_a],
            side_b_player_ids=[side_b],
            cutoff_at="2026-07-10T00:00:00+00:00",
        )

    def test_equal_probability_is_control_benchmark(self) -> None:
        self.add_history(1, 20, 9)
        self.add_history(2, 20, 6)
        prediction = score_matchup(self.matchup(1, 2), model_version="equal-v1")
        self.assertEqual(prediction["sideAProbability"], 0.5)
        self.assertEqual(prediction["sideBProbability"], 0.5)
        self.assertEqual(prediction["evidenceTier"], "C")

    def test_ppr_model_is_symmetric_when_sides_are_reversed(self) -> None:
        self.add_history(1, 20, 9)
        self.add_history(2, 20, 6)
        forward = score_matchup(
            self.matchup(1, 2),
            model_version="ppr-difference-v1",
        )
        reverse = score_matchup(
            self.matchup(2, 1),
            model_version="ppr-difference-v1",
        )
        self.assertAlmostEqual(
            forward["sideAProbability"],
            reverse["sideBProbability"],
            places=6,
        )
        self.assertAlmostEqual(
            forward["sideBProbability"],
            reverse["sideAProbability"],
            places=6,
        )

    def test_tier_c_probability_is_shrunk_toward_even(self) -> None:
        self.add_history(1, 20, 9)
        self.add_history(2, 20, 6)
        prediction = score_matchup(
            self.matchup(1, 2),
            model_version="ppr-difference-v1",
        )
        self.assertEqual(prediction["evidenceTier"], "C")
        self.assertEqual(prediction["shrinkageFactor"], 0.2)
        self.assertGreater(prediction["rawSideAProbability"], prediction["sideAProbability"])
        self.assertGreater(prediction["sideAProbability"], 0.5)

    def test_tier_b_uses_unshrunk_benchmark_probability(self) -> None:
        self.add_history(1, 100, 9)
        self.add_history(2, 100, 6)
        prediction = score_matchup(
            self.matchup(1, 2),
            model_version="ppr-difference-v1",
        )
        self.assertEqual(prediction["evidenceTier"], "B")
        self.assertEqual(prediction["shrinkageFactor"], 1.0)
        self.assertEqual(
            prediction["rawSideAProbability"],
            prediction["sideAProbability"],
        )

    def test_missing_player_history_causes_abstention(self) -> None:
        self.add_history(1, 20, 9)
        prediction = score_matchup(
            self.matchup(1, 999),
            model_version="ppr-difference-v1",
        )
        self.assertEqual(prediction["status"], "ABSTAINED")
        self.assertEqual(prediction["evidenceTier"], "NO_PREDICTION")
        self.assertIsNone(prediction["sideAProbability"])

    def test_prediction_records_are_append_only(self) -> None:
        self.add_history(1, 20, 9)
        self.add_history(2, 20, 6)
        first = create_prediction(
            self.conn,
            side_a_player_ids=[1],
            side_b_player_ids=[2],
            cutoff_at="2026-07-10T00:00:00+00:00",
            model_version="ppr-difference-v1",
            event_id=10,
            match_id=5,
        )
        second = create_prediction(
            self.conn,
            side_a_player_ids=[1],
            side_b_player_ids=[2],
            cutoff_at="2026-07-10T00:00:00+00:00",
            model_version="ppr-difference-v1",
            event_id=10,
            match_id=5,
        )
        self.assertNotEqual(first["predictionId"], second["predictionId"])
        rows = self.conn.execute(
            "SELECT * FROM prediction_records ORDER BY prediction_id"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["feature_hash"], rows[1]["feature_hash"])
        self.assertEqual(rows[0]["features_json"], rows[1]["features_json"])


if __name__ == "__main__":
    unittest.main()
