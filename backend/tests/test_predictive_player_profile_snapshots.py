import json
import sqlite3
import unittest

from predictive_player_profile import (
    _profile_data_scope,
    _store_player_analytics_snapshots,
    initialize_player_analytics_snapshot_schema,
)


class PredictivePlayerProfileSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE player_rounds(
                player_id INTEGER, event_id INTEGER, match_id TEXT,
                game_id INTEGER, event_date TEXT
            );
            CREATE TABLE games(
                event_id INTEGER, match_id TEXT, game_id INTEGER,
                completed INTEGER,
                PRIMARY KEY(event_id, match_id, game_id)
            );
            """
        )
        initialize_player_analytics_snapshot_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_base_refresh_preserves_existing_advanced_profile(self) -> None:
        _store_player_analytics_snapshots(
            self.conn,
            [{
                "playerId": 142125,
                "profileStage": "FULL_READY",
                "profileRatings": {"currentFormRating": 70},
                "clutchProfile": {"clutchRating": 82},
            }],
            stage="FULL_READY",
        )

        _store_player_analytics_snapshots(
            self.conn,
            [{
                "playerId": 142125,
                "profileStage": "BASE_READY",
                "profileRatings": {"currentFormRating": 75},
            }],
            stage="BASE_READY",
        )

        row = self.conn.execute(
            "SELECT snapshot_json, snapshot_stage FROM player_analytics_snapshots WHERE player_id=142125"
        ).fetchone()
        payload = json.loads(row["snapshot_json"])
        self.assertEqual(row["snapshot_stage"], "FULL_READY")
        self.assertEqual(payload["profileStage"], "FULL_READY")
        self.assertEqual(payload["profileRatings"]["currentFormRating"], 75)
        self.assertEqual(payload["clutchProfile"]["clutchRating"], 82)

    def test_data_scope_explains_every_excluded_round(self) -> None:
        self.conn.executemany(
            "INSERT INTO player_rounds VALUES (1, ?, '1', 1, ?)",
            [
                (10, "2026-08-01T00:00:00+00:00"),
                (11, "2026-08-01T00:00:00+00:00"),
                (12, None),
                (13, "2024-01-01T00:00:00+00:00"),
            ],
        )
        self.conn.execute("INSERT INTO games VALUES (10, '1', 1, 1)")
        self.conn.execute("INSERT INTO games VALUES (11, '1', 1, 0)")

        scope = _profile_data_scope(
            self.conn,
            1,
            cutoff_at="2026-08-24T00:00:00+00:00",
            window_days=365,
        )

        self.assertEqual(scope["collectedRounds"], 4)
        self.assertEqual(scope["includedRounds"], 1)
        self.assertEqual(scope["excludedRounds"], 3)
        self.assertEqual(scope["exclusions"]["missingEventDate"], 1)
        self.assertEqual(scope["exclusions"]["outsideWindow"], 1)
        self.assertEqual(scope["exclusions"]["incompleteGame"], 1)


if __name__ == "__main__":
    unittest.main()

