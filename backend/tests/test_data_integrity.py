from __future__ import annotations

import sqlite3
import json
import tempfile
import unittest
from pathlib import Path

from data_integrity import inspect_match_payload, integrity_summary
from integrity_backfill import audit_cached_match_stats
from provenance import record_source_payload
from season_platform import init_db


class DataIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_rejects_duplicate_players_invalid_bags_and_detail_mismatch(self) -> None:
        payload = {
            "event_match_inning_history": [
                {"inningno": 1, "playerid": 10, "teamid": 1, "totalpoints": 8, "bagsin": 2, "bagson": 2, "bagsoff": 0},
                {"inningno": 1, "playerid": 10, "teamid": 1, "totalpoints": 20, "bagsin": 4, "bagson": 2, "bagsoff": 0},
            ],
            "event_match_details": [{"playerid": 10, "playedinnings": 3, "totalpts": 99}],
        }
        result = inspect_match_payload(payload, completed=True)
        codes = {error["code"] for error in result["errors"]}
        self.assertFalse(result["passed"])
        self.assertIn("DUPLICATE_PLAYER_ROUND", codes)
        self.assertIn("IMPOSSIBLE_ROUND_SCORE", codes)
        self.assertIn("INVALID_BAG_TOTAL", codes)
        self.assertIn("ROUND_SAME_TEAM", codes)
        self.assertIn("PLAYER_ROUND_TOTAL_MISMATCH", codes)
        self.assertIn("PLAYER_POINT_TOTAL_MISMATCH", codes)

    def test_rejects_round_gaps_and_player_team_switches(self) -> None:
        payload = {
            "event_match_inning_history": [
                {"inningno": 1, "playerid": 10, "teamid": 1, "totalpoints": 8},
                {"inningno": 1, "playerid": 20, "teamid": 2, "totalpoints": 7},
                {"inningno": 3, "playerid": 10, "teamid": 2, "totalpoints": 6},
                {"inningno": 3, "playerid": 20, "teamid": 1, "totalpoints": 5},
            ]
        }
        result = inspect_match_payload(payload, completed=True)
        codes = {error["code"] for error in result["errors"]}
        self.assertIn("ROUND_SEQUENCE_GAP", codes)
        self.assertIn("PLAYER_TEAM_CHANGED", codes)

    def test_singles_allows_acl_placeholder_team_ids(self) -> None:
        payload = {
            "event_match_inning_history": [
                {"inningno": 1, "playerid": 10, "teamid": -1, "totalpoints": 8},
                {"inningno": 1, "playerid": 20, "teamid": -1, "totalpoints": 7},
            ]
        }
        result = inspect_match_payload(payload, completed=True, match_type="S")
        self.assertTrue(result["passed"])

    def test_empty_database_has_versioned_integrity_status(self) -> None:
        status = integrity_summary(self.conn)
        self.assertEqual(status["integrityVersion"], "data-integrity-v2.0")
        self.assertEqual(status["analyticsReady"], 0)
        self.assertEqual(status["blocked"], 0)
        self.assertEqual(status["legacyUnverifiedGames"], 0)
        self.assertTrue(status["migrationReady"])

    def test_backfill_is_dry_run_by_default_and_idempotent_when_applied(self) -> None:
        payload = {
            "matchStatus": 5,
            "event_match_inning_history": [
                {"inningno": 1, "playerid": 10, "teamid": 1, "totalpoints": 8, "bagsin": 1, "bagson": 3, "bagsoff": 0},
                {"inningno": 1, "playerid": 20, "teamid": 2, "totalpoints": 7, "bagsin": 0, "bagson": 4, "bagsoff": 0},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "event_88_match_4_game_1_stats.json").write_text(json.dumps(payload), encoding="utf-8")
            dry = audit_cached_match_stats(self.conn, directory)
            self.assertEqual(dry["validated"], 1)
            self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM player_rounds").fetchone()[0], 0)

            applied = audit_cached_match_stats(self.conn, directory, apply=True)
            self.assertEqual(applied["validated"], 1)
            self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM player_rounds").fetchone()[0], 2)

            repeated = audit_cached_match_stats(self.conn, directory, apply=True)
            self.assertEqual(repeated["alreadyCurrent"], 1)
            self.assertEqual(repeated["validated"], 0)

    def test_backfill_uses_verified_payload_archive_when_loose_file_is_absent(self) -> None:
        payload = {
            "matchStatus": 5,
            "event_match_inning_history": [
                {"inningno": 1, "playerid": 10, "teamid": 1, "totalpoints": 8, "playerfirstname": "José"},
                {"inningno": 1, "playerid": 20, "teamid": 2, "totalpoints": 7},
            ],
        }
        record_source_payload(
            self.conn,
            source_endpoint="match-stats",
            entity_key="match-stats:91:7:1",
            request_url=None,
            payload=payload,
        )
        with tempfile.TemporaryDirectory() as directory:
            result = audit_cached_match_stats(self.conn, directory)
        self.assertEqual(result["filesDiscovered"], 0)
        self.assertEqual(result["archivePayloadsDiscovered"], 1)
        self.assertEqual(result["sourcesDiscovered"], 1)
        self.assertEqual(result["validated"], 1)
        self.assertEqual(result["games"][0]["source"], "source_payload:1")

    def test_status_exposes_legacy_rows_until_their_raw_source_is_certified(self) -> None:
        self.conn.execute(
            """
            INSERT INTO player_rounds(
                event_id,match_id,game_id,round_no,player_id,player_name,
                gross_points,opponent_points,net_points,scored_points,
                bags_in,bags_on,bags_off,four_bagger,round_result
            ) VALUES (7,'9',1,1,42,'Legacy Player',8,7,1,1,1,3,0,0,'W')
            """
        )
        status = integrity_summary(self.conn)
        self.assertEqual(status["legacyUnverifiedGames"], 1)
        self.assertFalse(status["migrationReady"])


if __name__ == "__main__":
    unittest.main()
