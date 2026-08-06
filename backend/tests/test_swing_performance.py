import sqlite3
import unittest

from swing_performance import swing_performance_ratings


class SwingPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("""
            CREATE TABLE player_rounds (
                event_id INTEGER, match_id TEXT, game_id INTEGER, round_no INTEGER,
                player_id INTEGER, team_id TEXT, net_points INTEGER, event_date TEXT
            )
        """)

    def tearDown(self):
        self.conn.close()

    def _round(self, event, round_no, p1_net, p2_net):
        date = f"2026-01-{event:02d}"
        self.conn.executemany(
            "INSERT INTO player_rounds VALUES (?,?,?,?,?,?,?,?)",
            [
                (event, "1", 1, round_no, 1, "A", p1_net, date),
                (event, "1", 1, round_no, 2, "B", p2_net, date),
            ],
        )

    def test_same_deficit_is_more_surprising_for_stable_player(self):
        # Establish a strong/stable baseline for player 1 and a volatile one for player 2.
        for event in range(1, 8):
            self._round(event, 1, 2, -2)
            self._round(event, 2, 1, -1)
        for event in range(8, 13):
            self._round(event, 1, -7, 7)
            self._round(event, 2, 3, -3)
        ratings = swing_performance_ratings(self.conn, minimum_exposures=1)
        self.assertGreater(ratings[1]["averageSwingSurprise"], 0)
        self.assertEqual(ratings[1]["largeSwings"], 5)
        self.assertEqual(ratings[1]["severeSwings"], 5)

    def test_recovery_uses_next_recorded_round(self):
        for event in range(1, 7):
            self._round(event, 1, -7, 7)
            self._round(event, 2, 4, -4)
        ratings = swing_performance_ratings(self.conn, minimum_exposures=1)
        self.assertEqual(ratings[1]["recoveryOpportunities"], 6)
        self.assertGreater(ratings[1]["recoveryRate"], 0)

    def test_partner_opponent_and_outcome_follow_the_swing_sequence(self):
        for event in range(1, 7):
            date = f"2026-02-{event:02d}"
            self.conn.executemany(
                "INSERT INTO player_rounds VALUES (?,?,?,?,?,?,?,?)",
                [
                    # Player 1 gives up seven; opponent 3 creates the swing.
                    (event, "2", 1, 1, 1, "A", -7, date),
                    (event, "2", 1, 1, 3, "B", 7, date),
                    # Partner 2 responds positively and opponent 4 gives points back.
                    (event, "2", 1, 2, 2, "A", 4, date),
                    (event, "2", 1, 2, 4, "B", -4, date),
                    # Player 1 later completes the comeback.
                    (event, "2", 1, 3, 1, "A", 8, date),
                    (event, "2", 1, 3, 3, "B", -8, date),
                ],
            )
        ratings = swing_performance_ratings(self.conn, minimum_exposures=1)
        player = ratings[1]
        self.assertEqual(player["partnerResponseOpportunities"], 6)
        self.assertEqual(player["partnerPositiveResponseRate"], 1.0)
        self.assertEqual(player["opponentGivebackRate"], 1.0)
        self.assertEqual(player["opponentFollowThroughRate"], 0.0)
        self.assertEqual(player["comebackWinRateAfterSwing"], 1.0)


if __name__ == "__main__":
    unittest.main()
