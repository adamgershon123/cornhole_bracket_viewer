import sqlite3
import unittest

from profile_ratings import profile_ratings


class ProfileRatingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE player_rounds(
                player_id INTEGER, event_date TEXT, event_id INTEGER,
                match_id TEXT, game_id INTEGER, round_no INTEGER,
                gross_points REAL, net_points REAL, round_result TEXT
            )
            """
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_small_sample_consistency_is_provisional_and_shrunk(self) -> None:
        self.conn.executemany(
            "INSERT INTO player_rounds VALUES (1, '2026-01-01', 1, '1', 1, ?, 8, 0, 'W')",
            [(round_no,) for round_no in range(1, 31)],
        )
        self.conn.executemany(
            "INSERT INTO player_rounds VALUES (2, '2026-01-01', 1, '2', 1, ?, ?, 0, 'W')",
            [
                (round_no, 7 if round_no % 2 else 8)
                for round_no in range(1, 201)
            ],
        )

        ratings = profile_ratings(self.conn)

        self.assertTrue(ratings[1]["consistencyProvisional"])
        self.assertEqual(ratings[1]["consistencyLabel"], "Provisional")
        self.assertFalse(ratings[2]["consistencyProvisional"])
        self.assertGreater(ratings[1]["adjustedRoundPprStdDev"], 0)
        self.assertLess(ratings[1]["consistencyReliability"], 0.5)


if __name__ == "__main__":
    unittest.main()
