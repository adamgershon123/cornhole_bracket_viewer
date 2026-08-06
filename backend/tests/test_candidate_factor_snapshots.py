import sqlite3
import unittest

from candidate_factor_snapshots import build_candidate_factor_snapshot
from season_platform import init_db


class CandidateFactorSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.conn.execute(
            """
            INSERT INTO player_rounds(
                event_id, match_id, game_id, round_no, player_id, event_date,
                team_id, gross_points, opponent_points, net_points, round_result,
                bags_in, bags_on, bags_off, four_bagger
            ) VALUES (1, '1', 1, 1, 10, '2026-01-01', 'A', 9, 8, 1, 'W', 2, 2, 0, 0)
            """
        )
        self.conn.execute(
            """
            INSERT INTO player_rounds(
                event_id, match_id, game_id, round_no, player_id, event_date,
                team_id, gross_points, opponent_points, net_points, round_result,
                bags_in, bags_on, bags_off, four_bagger
            ) VALUES (2, '1', 1, 1, 10, '2026-03-01', 'A', 12, 4, 8, 'W', 4, 0, 0, 1)
            """
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_snapshot_excludes_rounds_on_or_after_cutoff(self):
        snapshot = build_candidate_factor_snapshot(
            self.conn,
            side_a_player_ids=[10],
            side_b_player_ids=[20],
            cutoff_at="2026-02-01T12:00:00+00:00",
        )
        self.assertEqual(snapshot["cutoffPolicy"], "STRICTLY_PRIOR_EVENT_DATE")
        self.assertEqual(snapshot["expectedFactors"], 16)
        self.assertTrue(snapshot["missingReasons"])
        # With only one prior round, form is unavailable. The later strong round
        # must not make it cross the minimum sample threshold.
        self.assertFalse(
            snapshot["playerFactors"]["10"]["currentForm"]["available"]
        )


if __name__ == "__main__":
    unittest.main()
