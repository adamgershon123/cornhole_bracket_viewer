import sqlite3
import unittest

from match_profile_trajectory import match_profile_trajectories
from season_platform import init_db


class MatchProfileTrajectoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.conn.execute(
            "INSERT INTO events(event_id,event_date) VALUES (1,'2026-07-01')"
        )
        self.conn.execute(
            "INSERT INTO players(player_id,display_name) VALUES (10,'Player Ten')"
        )
        for round_no, points in enumerate((7, 8, 7, 7), start=1):
            self.conn.execute(
                """
                INSERT INTO player_rounds(
                    event_id,match_id,game_id,round_no,player_id,event_date,
                    team_id,gross_points,opponent_points,net_points,round_result,
                    bags_in,bags_on,bags_off,four_bagger
                ) VALUES (?,?,?,?,?,'2026-06-01','A',?,?,?,'W',2,2,0,0)
                """,
                (2, "1", 1, round_no, 10, points, 6, points - 6),
            )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_season_ppr_moves_from_pre_event_baseline_through_rounds(self):
        result = match_profile_trajectories(
            self.conn,
            event_id=1,
            rounds=[
                {
                    "round": 1,
                    "players": [
                        {
                            "playerId": "10", "teamId": "A", "name": "Player Ten",
                            "grossPoints": 8, "bagsIn": 2, "bagsOn": 2, "bagsOff": 0,
                        },
                        {"playerId": "20", "teamId": "B", "grossPoints": 6},
                    ],
                }
            ],
        )
        player = next(item for item in result["players"] if item["playerId"] == 10)
        baseline = next(
            metric for metric in player["snapshots"][0]["metrics"]
            if metric["key"] == "seasonPpr"
        )
        after = next(
            metric for metric in player["snapshots"][1]["metrics"]
            if metric["key"] == "seasonPpr"
        )
        self.assertEqual(baseline["before"], 7.25)
        self.assertEqual(after["current"], 7.4)
        self.assertEqual(after["direction"], "UP")


if __name__ == "__main__":
    unittest.main()
