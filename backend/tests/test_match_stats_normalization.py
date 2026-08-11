from __future__ import annotations

import sqlite3
import unittest

from season_platform import init_db, normalize_match_stats_to_rounds


def inning(number: int, player_id: int, team_id: int, points: int) -> dict:
    return {
        "inningno": number,
        "playerid": player_id,
        "teamid": team_id,
        "teamhomeaway": "H" if team_id == 1 else "A",
        "playerfirstname": f"Player{player_id}",
        "playerlastname": "Test",
        "totalpoints": points,
        "bagsin": 1,
        "bagson": 3,
        "bagsoff": 0,
    }


class MatchStatsNormalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_completed_snapshot_replaces_partial_live_history(self) -> None:
        live = {
            "matchStatus": 3,
            "event_match_inning_history": [
                inning(1, 10, 1, 10),
                inning(1, 20, 2, 4),
            ],
        }
        normalize_match_stats_to_rounds(self.conn, 100, "17", 1, live)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM player_rounds").fetchone()[0],
            2,
        )

        final = {
            "matchStatus": 5,
            "event_match_inning_history": [
                inning(round_no, 10, 1, 7 + round_no)
                if row_no % 2 == 0
                else inning(round_no, 20, 2, 6 + round_no)
                for round_no in range(1, 7)
                for row_no in range(2)
            ],
        }
        normalize_match_stats_to_rounds(self.conn, 100, "17", 1, final)

        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM player_rounds").fetchone()[0],
            12,
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM rounds").fetchone()[0],
            6,
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT gross_points FROM player_rounds WHERE round_no=1 AND player_id=10"
            ).fetchone()[0],
            8,
        )


if __name__ == "__main__":
    unittest.main()
