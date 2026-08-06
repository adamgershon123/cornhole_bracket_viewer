from __future__ import annotations

import sqlite3
import unittest

from provenance import record_ingestion_attempt
from season_platform import init_db
from stage_a_features import (
    build_matchup_features,
    build_partnership_features,
    build_player_features,
)


class StageAFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def add_event(self, event_id: int, event_date: str) -> None:
        self.conn.execute(
            "INSERT INTO events(event_id, event_date) VALUES (?, ?)",
            (event_id, event_date),
        )

    def add_game(
        self,
        event_id: int,
        match_id: str,
        game_id: int,
        home_team_id: str,
        away_team_id: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO games(
                event_id, match_id, game_id, home_team_id, away_team_id, completed
            ) VALUES (?, ?, ?, ?, ?, 1)
            """,
            (event_id, match_id, game_id, home_team_id, away_team_id),
        )

    def add_round(
        self,
        *,
        event_id: int,
        event_date: str,
        match_id: str,
        game_id: int,
        round_no: int,
        player_id: int,
        team_id: str,
        gross: int,
        opponent: int,
        bags_in: int,
        bags_on: int,
        bags_off: int,
        match_type: str = "D",
        bracket_type: str = "W",
    ) -> None:
        net = gross - opponent
        self.conn.execute(
            """
            INSERT INTO player_rounds(
                event_id, match_id, game_id, round_no, player_id, team_id,
                gross_points, opponent_points, net_points, scored_points,
                bags_in, bags_on, bags_off, four_bagger, round_result,
                event_date, match_type, bracket_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                match_id,
                game_id,
                round_no,
                player_id,
                team_id,
                gross,
                opponent,
                net,
                max(net, 0),
                bags_in,
                bags_on,
                bags_off,
                1 if bags_in == 4 else 0,
                "W" if net > 0 else "L" if net < 0 else "T",
                event_date,
                match_type,
                bracket_type,
            ),
        )

    def test_player_features_exclude_cutoff_day_and_future_events(self) -> None:
        for event_id, event_date in ((1, "2026-07-01"), (2, "2026-07-10"), (3, "2026-07-11")):
            self.add_event(event_id, event_date)
            self.add_game(event_id, "1", 1, f"{event_id}:5", f"{event_id}:6")
            self.conn.execute(
                "INSERT INTO team_members(team_id, player_id, event_id) VALUES (?, 1, ?)",
                (f"{event_id}:5", event_id),
            )
        self.add_round(
            event_id=1,
            event_date="2026-07-01",
            match_id="1",
            game_id=1,
            round_no=1,
            player_id=1,
            team_id="1:5",
            gross=9,
            opponent=6,
            bags_in=3,
            bags_on=0,
            bags_off=1,
        )
        self.add_round(
            event_id=1,
            event_date="2026-07-01",
            match_id="1",
            game_id=1,
            round_no=2,
            player_id=1,
            team_id="1:5",
            gross=6,
            opponent=8,
            bags_in=2,
            bags_on=0,
            bags_off=2,
        )
        for event_id, event_date in ((2, "2026-07-10"), (3, "2026-07-11")):
            self.add_round(
                event_id=event_id,
                event_date=event_date,
                match_id="1",
                game_id=1,
                round_no=1,
                player_id=1,
                team_id=f"{event_id}:5",
                gross=12,
                opponent=0,
                bags_in=4,
                bags_on=0,
                bags_off=0,
            )
        self.conn.commit()

        features = build_player_features(
            self.conn,
            player_id=1,
            cutoff_at="2026-07-10T18:00:00-04:00",
            window_days=365,
        )

        self.assertEqual(features["rounds"], 2)
        self.assertEqual(features["grossPoints"], 15)
        self.assertEqual(features["calculatedPpr"], 7.5)
        self.assertEqual(features["calculatedDpr"], 0.5)
        self.assertEqual(features["lastEventDate"], "2026-07-01")
        self.assertEqual(features["cutoffPolicy"], "STRICTLY_PRIOR_EVENT_DATE")

    def test_late_local_cutoff_does_not_advance_event_date_in_utc(self) -> None:
        self.add_event(1, "2026-07-25")
        self.add_round(
            event_id=1,
            event_date="2026-07-25",
            match_id="1",
            game_id=1,
            round_no=1,
            player_id=1,
            team_id="1:5",
            gross=12,
            opponent=0,
            bags_in=4,
            bags_on=0,
            bags_off=0,
        )
        self.conn.commit()

        features = build_player_features(
            self.conn,
            player_id=1,
            cutoff_at="2026-07-25T23:59:59-04:00",
        )

        self.assertEqual(features["dataCutoffAt"], "2026-07-26T03:59:59+00:00")
        self.assertEqual(features["cutoffEventDate"], "2026-07-25")
        self.assertEqual(features["rounds"], 0)

    def test_coverage_counts_expected_retrieved_and_auth_blocked_games(self) -> None:
        for event_id in (1, 2):
            self.add_event(event_id, f"2026-07-0{event_id}")
            self.add_game(event_id, "1", 1, f"{event_id}:5", f"{event_id}:6")
            self.conn.execute(
                "INSERT INTO team_members(team_id, player_id, event_id) VALUES (?, 1, ?)",
                (f"{event_id}:5", event_id),
            )
        self.add_round(
            event_id=1,
            event_date="2026-07-01",
            match_id="1",
            game_id=1,
            round_no=1,
            player_id=1,
            team_id="1:5",
            gross=9,
            opponent=6,
            bags_in=3,
            bags_on=0,
            bags_off=1,
        )
        record_ingestion_attempt(
            self.conn,
            source_endpoint="match-stats",
            entity_key="match-stats:1:1:1",
            outcome="success",
        )
        record_ingestion_attempt(
            self.conn,
            source_endpoint="match-stats",
            entity_key="match-stats:2:1:1",
            outcome="auth_blocked",
            http_status=403,
        )
        self.conn.commit()

        coverage = build_player_features(
            self.conn,
            player_id=1,
            cutoff_at="2026-07-10T00:00:00+00:00",
        )["coverage"]

        self.assertTrue(coverage["coverageKnown"])
        self.assertEqual(coverage["expectedGames"], 2)
        self.assertEqual(coverage["indexedExpectedGames"], 2)
        self.assertEqual(coverage["retrievedGames"], 1)
        self.assertEqual(coverage["blockedGames"], 1)
        self.assertEqual(coverage["coverageRatio"], 0.5)

    def test_incomplete_expected_index_does_not_publish_invalid_ratio(self) -> None:
        self.add_event(1, "2026-07-01")
        self.add_round(
            event_id=1,
            event_date="2026-07-01",
            match_id="unindexed",
            game_id=1,
            round_no=1,
            player_id=1,
            team_id="1:5",
            gross=9,
            opponent=6,
            bags_in=3,
            bags_on=0,
            bags_off=1,
        )
        self.conn.commit()

        coverage = build_player_features(
            self.conn,
            player_id=1,
            cutoff_at="2026-07-10T00:00:00+00:00",
        )["coverage"]

        self.assertFalse(coverage["coverageKnown"])
        self.assertIsNone(coverage["expectedGames"])
        self.assertEqual(coverage["indexedExpectedGames"], 0)
        self.assertEqual(coverage["retrievedGames"], 1)
        self.assertIsNone(coverage["coverageRatio"])

    def test_partnership_is_detected_across_alternating_rounds(self) -> None:
        self.add_event(1, "2026-07-01")
        self.add_game(1, "1", 1, "1:5", "1:6")
        self.add_round(
            event_id=1,
            event_date="2026-07-01",
            match_id="1",
            game_id=1,
            round_no=1,
            player_id=1,
            team_id="1:5",
            gross=9,
            opponent=6,
            bags_in=3,
            bags_on=0,
            bags_off=1,
        )
        self.add_round(
            event_id=1,
            event_date="2026-07-01",
            match_id="1",
            game_id=1,
            round_no=2,
            player_id=2,
            team_id="1:5",
            gross=7,
            opponent=5,
            bags_in=2,
            bags_on=1,
            bags_off=1,
        )
        self.conn.commit()

        partnership = build_partnership_features(
            self.conn,
            player_ids=[1, 2],
            cutoff_at="2026-07-10T00:00:00+00:00",
        )
        self.assertTrue(partnership["knownPartnership"])
        self.assertEqual(partnership["sharedGames"], 1)
        self.assertEqual(partnership["sharedEvents"], 1)

    def test_matchup_builds_side_a_minus_b_deltas(self) -> None:
        self.add_event(1, "2026-07-01")
        self.add_game(1, "1", 1, "1:5", "1:6")
        self.add_round(
            event_id=1,
            event_date="2026-07-01",
            match_id="1",
            game_id=1,
            round_no=1,
            player_id=1,
            team_id="1:5",
            gross=9,
            opponent=6,
            bags_in=3,
            bags_on=0,
            bags_off=1,
        )
        self.add_round(
            event_id=1,
            event_date="2026-07-01",
            match_id="1",
            game_id=1,
            round_no=1,
            player_id=3,
            team_id="1:6",
            gross=6,
            opponent=9,
            bags_in=2,
            bags_on=0,
            bags_off=2,
        )
        self.conn.commit()

        matchup = build_matchup_features(
            self.conn,
            side_a_player_ids=[1],
            side_b_player_ids=[3],
            cutoff_at="2026-07-10T00:00:00+00:00",
        )
        self.assertTrue(matchup["modelReady"])
        self.assertEqual(matchup["deltasAminusB"]["calculatedPpr"], 3.0)
        self.assertEqual(matchup["deltasAminusB"]["calculatedDpr"], 6.0)


if __name__ == "__main__":
    unittest.main()
