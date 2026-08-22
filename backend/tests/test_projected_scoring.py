import random
import sqlite3
import unittest

from projected_scoring import (
    ScoreCalibration,
    load_score_calibration,
    projected_score,
    sample_score,
)


class ProjectedScoringTests(unittest.TestCase):
    def test_calibration_is_cutoff_safe(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript(
            """
            CREATE TABLE events(event_id INTEGER PRIMARY KEY, event_date TEXT);
            CREATE TABLE games(
                event_id INTEGER, completed INTEGER,
                home_score INTEGER, away_score INTEGER
            );
            INSERT INTO events VALUES (1, '2026-01-01'), (2, '2026-03-01');
            INSERT INTO games VALUES (1, 1, 21, 10), (2, 1, 21, 0);
            """
        )
        calibration = load_score_calibration(conn, cutoff_date="2026-02-01")
        self.assertEqual(calibration.sample_size, 1)
        self.assertEqual(calibration.average_margin, 11)

    def test_stronger_favorite_projects_larger_margin(self):
        calibration = ScoreCalibration(100, 21, 14, 7, 6, 4)
        even = projected_score(0.5, calibration)
        favorite = projected_score(0.85, calibration)
        self.assertGreater(favorite["favoriteMargin"], even["favoriteMargin"])
        self.assertEqual(favorite["sideAScore"], 21)

    def test_sampled_score_agrees_with_sampled_winner(self):
        calibration = ScoreCalibration(100, 21, 14, 7, 6, 4)
        a_score, b_score = sample_score(
            winner_is_side_a=False,
            side_a_probability=0.3,
            calibration=calibration,
            rng=random.Random(7),
        )
        self.assertGreater(b_score, a_score)


if __name__ == "__main__":
    unittest.main()
