from __future__ import annotations

import sqlite3
import unittest

from feature_quality_audit import (
    feature_anomalies,
    provisional_evidence_tier,
    run_feature_quality_audit,
)
from season_platform import init_db


class FeatureQualityAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def add_history(self, player_id: int, rounds: int, gross: int = 8) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO events(event_id, event_date) VALUES (1, '2026-07-01')"
        )
        for round_no in range(1, rounds + 1):
            self.conn.execute(
                """
                INSERT INTO player_rounds(
                    event_id, match_id, game_id, round_no, player_id, team_id,
                    gross_points, opponent_points, net_points, scored_points,
                    bags_in, bags_on, bags_off, four_bagger, round_result,
                    event_date, match_type, bracket_type
                ) VALUES (1, ?, ?, ?, ?, ?, ?, 7, ?, ?, 2, 2, 0, 0, 'W',
                          '2026-07-01', 'D', 'W')
                """,
                (
                    str((round_no - 1) // 10 + 1),
                    (round_no - 1) // 10 + 1,
                    round_no,
                    player_id,
                    f"1:{player_id}",
                    gross,
                    gross - 7,
                    max(gross - 7, 0),
                ),
            )
        self.conn.commit()

    def test_provisional_tiers_do_not_require_acl_for_b(self) -> None:
        self.add_history(1, 100)
        from stage_a_features import build_player_features

        features = build_player_features(
            self.conn,
            player_id=1,
            cutoff_at="2026-07-10T00:00:00+00:00",
            include_acl_snapshots=True,
        )
        self.assertEqual(provisional_evidence_tier(features), "B")

    def test_anomaly_checks_reject_impossible_rates(self) -> None:
        anomalies = feature_anomalies({
            "rounds": 1,
            "calculatedPpr": 13,
            "calculatedOpponentPpr": 7,
            "calculatedDpr": 6,
            "bagsInRate": 1.2,
            "bagsOnRate": 0,
            "bagsOffRate": 0,
            "fourBaggerRate": 0,
            "roundWinRate": 1,
            "roundLossRate": 0,
            "roundTieRate": 0,
            "coverage": {"coverageRatio": 1.1},
        })
        self.assertIn("calculatedPpr:outside_0_12", anomalies)
        self.assertIn("bagsInRate:outside_0_1", anomalies)
        self.assertIn("coverageRatio:outside_0_1", anomalies)

    def test_repository_audit_summarizes_tiers_and_formats(self) -> None:
        self.add_history(1, 100)
        self.add_history(2, 20, gross=6)
        report = run_feature_quality_audit(
            self.conn,
            cutoff_at="2026-07-10T00:00:00+00:00",
            player_ids=[1, 2],
        )
        self.assertEqual(report["playersAudited"], 2)
        self.assertEqual(report["evidenceTiers"]["B"], 1)
        self.assertEqual(report["evidenceTiers"]["C"], 1)
        self.assertEqual(report["formatsByRoundCount"]["D:W"], 120)
        self.assertEqual(report["anomalies"]["playersWithAnomalies"], 0)
        self.assertTrue(report["baselineBuildReady"])


if __name__ == "__main__":
    unittest.main()
