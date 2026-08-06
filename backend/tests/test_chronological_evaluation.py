from __future__ import annotations

import sqlite3
import unittest

from chronological_evaluation import evaluate_benchmarks, historical_matchups
from season_platform import init_db


class ChronologicalEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def add_event(self, event_id: int, event_date: str) -> None:
        self.conn.execute(
            "INSERT INTO events(event_id, event_date, match_type, bracket_type) "
            "VALUES (?, ?, 'S', 'D')",
            (event_id, event_date),
        )

    def add_game(
        self,
        event_id: int,
        match_id: str,
        home_score: int,
        away_score: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO games(
                event_id, match_id, game_id, home_team_id, away_team_id,
                home_score, away_score, completed
            ) VALUES (?, ?, 1, ?, ?, ?, ?, 1)
            """,
            (
                event_id,
                match_id,
                f"{event_id}:1",
                f"{event_id}:2",
                home_score,
                away_score,
            ),
        )

    def add_round(
        self,
        *,
        event_id: int,
        event_date: str,
        match_id: str,
        round_no: int,
        player_id: int,
        side: str,
        gross: int,
        opponent: int,
    ) -> None:
        team = "1" if side == "HOME" else "2"
        net = gross - opponent
        self.conn.execute(
            """
            INSERT INTO player_rounds(
                event_id, match_id, game_id, round_no, player_id, team_id,
                team_side, gross_points, opponent_points, net_points,
                scored_points, bags_in, bags_on, bags_off, four_bagger,
                round_result, event_date, match_type, bracket_type
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      'S', 'D')
            """,
            (
                event_id,
                match_id,
                round_no,
                player_id,
                f"{event_id}:{team}",
                side,
                gross,
                opponent,
                net,
                max(net, 0),
                min(gross // 3, 4),
                0,
                4 - min(gross // 3, 4),
                1 if gross == 12 else 0,
                "W" if net > 0 else "L" if net < 0 else "T",
                event_date,
            ),
        )

    def add_prior_history(self) -> None:
        self.add_event(1, "2026-01-01")
        self.add_game(1, "1", 21, 10)
        for round_no in range(1, 101):
            self.add_round(
                event_id=1,
                event_date="2026-01-01",
                match_id="1",
                round_no=round_no,
                player_id=1,
                side="HOME",
                gross=9,
                opponent=6,
            )
            self.add_round(
                event_id=1,
                event_date="2026-01-01",
                match_id="1",
                round_no=round_no,
                player_id=2,
                side="AWAY",
                gross=6,
                opponent=9,
            )

    def add_target(self, player_a: int = 1, player_b: int = 2) -> None:
        self.add_event(2, "2026-02-01")
        self.add_game(2, "1", 21, 12)
        self.add_round(
            event_id=2,
            event_date="2026-02-01",
            match_id="1",
            round_no=1,
            player_id=player_a,
            side="HOME",
            gross=12,
            opponent=0,
        )
        self.add_round(
            event_id=2,
            event_date="2026-02-01",
            match_id="1",
            round_no=1,
            player_id=player_b,
            side="AWAY",
            gross=0,
            opponent=12,
        )
        self.conn.commit()

    def test_historical_matchup_reconstructs_recorded_sides_and_outcome(self) -> None:
        self.add_target(player_a=10, player_b=20)
        targets = historical_matchups(
            self.conn,
            start_date="2026-02-01",
            end_date="2026-02-01",
        )
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["sideAPlayerIds"], [10])
        self.assertEqual(targets[0]["sideBPlayerIds"], [20])
        self.assertEqual(targets[0]["sideAWon"], 1)

    def test_ppr_benchmark_uses_only_prior_event_history(self) -> None:
        self.add_prior_history()
        self.add_target()
        report = evaluate_benchmarks(
            self.conn,
            start_date="2026-02-01",
            end_date="2026-02-01",
        )
        ppr = report["models"]["ppr-difference-v1"]
        self.assertEqual(ppr["predictions"], 1)
        self.assertEqual(ppr["abstentions"], 0)
        self.assertGreater(
            report["commonSampleComparison"]["pprLogLossImprovement"],
            0,
        )
        self.assertGreater(
            report["commonSampleComparison"]["pprBrierImprovement"],
            0,
        )

    def test_new_players_cause_ppr_abstention_but_equal_control_remains(self) -> None:
        self.add_target(player_a=10, player_b=20)
        report = evaluate_benchmarks(
            self.conn,
            start_date="2026-02-01",
            end_date="2026-02-01",
        )
        self.assertEqual(report["models"]["equal-v1"]["predictions"], 1)
        self.assertEqual(report["models"]["ppr-difference-v1"]["predictions"], 0)
        self.assertEqual(report["models"]["ppr-difference-v1"]["abstentions"], 1)
        self.assertEqual(report["models"]["equal-v1"]["logLoss"], 0.693147)
        self.assertEqual(report["models"]["equal-v1"]["brierScore"], 0.25)


if __name__ == "__main__":
    unittest.main()
