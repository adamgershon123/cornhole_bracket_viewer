import sqlite3
import unittest

from performance_projections import (
    matchup_expected_performance,
    partnership_compatibility,
    rolling_ppr_profile,
)


class PerformanceProjectionTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE player_rounds (
                player_id INTEGER, event_id INTEGER, match_id TEXT, game_id INTEGER,
                team_id TEXT, round_no INTEGER, event_date TEXT,
                gross_points REAL, net_points REAL, round_result TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE games (
                event_id INTEGER, match_id TEXT, game_id INTEGER,
                completed INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(event_id, match_id, game_id)
            )
        """)
        for event_id, event_date in ((1, "2025-09-10"), (2, "2025-10-10")):
            self.conn.execute(
                "INSERT INTO games VALUES (?, '1', 1, 1)", (event_id,)
            )
            for round_no in range(1, 21):
                for player_id, gross in ((10, 8), (20, 7)):
                    self.conn.execute(
                        "INSERT INTO player_rounds VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (player_id, event_id, "1", 1, "A", round_no, event_date,
                         gross, 1 if player_id == 10 else -1, "W" if player_id == 10 else "L"),
                    )

    def tearDown(self):
        self.conn.close()

    def test_rolling_windows_retain_counts_and_cutoff(self):
        result = rolling_ppr_profile(
            self.conn, 10, cutoff_at="2025-11-01T00:00:00+00:00"
        )
        self.assertEqual(result["windows"]["season"]["rounds"], 40)
        self.assertEqual(result["windows"]["season"]["ppr"], 8)
        self.assertEqual(result["windows"]["last7Days"]["rounds"], 0)

    def test_partnership_reports_observed_effect_without_applying_it(self):
        result = partnership_compatibility(
            self.conn, [10, 20], cutoff_at="2025-11-01T00:00:00+00:00"
        )
        self.assertTrue(result["knownPartnership"])
        self.assertEqual(result["sharedGames"], 2)
        self.assertEqual(result["status"], "DESCRIPTIVE_ONLY_PENDING_INCREMENTAL_VALIDATION")

    def test_projection_keeps_unvalidated_partnership_weight_zero(self):
        result = matchup_expected_performance(
            self.conn, [10, 20], [10], cutoff_at="2025-11-01T00:00:00+00:00"
        )
        self.assertEqual(result["sideA"]["partnershipAdjustmentApplied"], 0)
        self.assertEqual(result["sideA"]["expectedPpr"], 7.5)
        dynamics = result["sideA"]["teamDynamics"]
        self.assertEqual(dynamics["strongerPlayerId"], 10)
        self.assertEqual(dynamics["weakerPlayerId"], 20)
        self.assertGreater(dynamics["partnerSkillGap"], 0)
        self.assertAlmostEqual(
            dynamics["carryBurden"],
            max(dynamics["requiredCarryPpr"] - dynamics["strongerExpectedPpr"], 0),
        )

    def test_incomplete_game_rounds_do_not_affect_projection_history(self):
        self.conn.execute("INSERT INTO games VALUES (3, '1', 1, 0)")
        self.conn.execute(
            "INSERT INTO player_rounds VALUES (?,?,?,?,?,?,?,?,?,?)",
            (10, 3, "1", 1, "A", 1, "2025-10-20", 0, -12, "L"),
        )
        result = rolling_ppr_profile(
            self.conn, 10, cutoff_at="2025-11-01T00:00:00+00:00"
        )
        self.assertEqual(result["windows"]["season"]["rounds"], 40)
        self.assertEqual(result["windows"]["season"]["ppr"], 8)


if __name__ == "__main__":
    unittest.main()
