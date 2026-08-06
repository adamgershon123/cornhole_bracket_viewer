from __future__ import annotations

import sqlite3
import unittest

from player_history_queue import (
    enqueue_players,
    process_player_history_queue,
    queued_history_report,
)
from season_platform import init_db


class PlayerHistoryQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_enqueue_deduplicates_players_and_accumulates_reasons(self) -> None:
        enqueue_players(
            self.conn,
            player_ids=[1, 2, 2],
            reason={"eventId": "10", "matchId": "1"},
            priority=20,
        )
        enqueue_players(
            self.conn,
            player_ids=[1],
            reason={"eventId": "11", "matchId": "2"},
            priority=10,
        )
        report = queued_history_report(self.conn)
        self.assertEqual(report["totalPlayers"], 2)
        row = self.conn.execute(
            "SELECT priority, reasons_json FROM player_history_queue WHERE player_id=1"
        ).fetchone()
        self.assertEqual(row["priority"], 10)
        self.assertIn('"eventId": "10"', row["reasons_json"])
        self.assertIn('"eventId": "11"', row["reasons_json"])

    def test_worker_marks_player_complete_from_round_coverage(self) -> None:
        enqueue_players(
            self.conn,
            player_ids=[1],
            reason={"eventId": "10"},
        )

        def collector(**kwargs):
            self.conn.execute(
                "INSERT OR IGNORE INTO events(event_id, event_date) VALUES (1, '2026-01-01')"
            )
            for round_no in range(1, 21):
                self.conn.execute(
                    """
                    INSERT INTO player_rounds(
                        event_id, match_id, game_id, round_no, player_id,
                        event_date
                    ) VALUES (1, '1', 1, ?, 1, '2026-01-01')
                    """,
                    (round_no,),
                )
            self.conn.commit()
            return {"manifest": {"coverage": {"matchStatsAuthBlocked": 2}}}

        result = process_player_history_queue(
            self.conn,
            collector=collector,
            minimum_rounds=20,
        )
        self.assertEqual(result["complete"], 1)
        player = result["players"][0]
        self.assertEqual(player["roundsAfter"], 20)
        self.assertEqual(player["authBlocked"], 2)

    def test_worker_keeps_insufficient_history_partial(self) -> None:
        enqueue_players(
            self.conn,
            player_ids=[9],
            reason={"eventId": "10"},
        )
        result = process_player_history_queue(
            self.conn,
            collector=lambda **kwargs: {"manifest": {"coverage": {}}},
            minimum_rounds=20,
        )
        self.assertEqual(result["partial"], 1)
        self.assertEqual(result["players"][0]["status"], "PARTIAL")


if __name__ == "__main__":
    unittest.main()
