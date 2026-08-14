import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from consolidate_tournament_stats import consolidate_tournament_stats
from match_stats_downloader import fetch_and_save_match_stats


class FakeResponse:
    status_code = 200
    headers = {"date": "Wed, 06 Aug 2026 00:00:00 GMT", "etag": "test-etag"}

    def json(self):
        return {
            "matchStatus": 0,
            "event_match_details": [],
            "event_match_inning_history": [],
        }


class LiveStatsDataDirectoryTests(unittest.TestCase):
    def test_match_stats_are_saved_to_configured_shared_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"DATA_DIR": temp_dir}), patch(
                "match_stats_downloader.fetch_match_stats_response",
                return_value=FakeResponse(),
            ):
                result = fetch_and_save_match_stats("123", [4], force=True)

            saved_path = Path(temp_dir) / "event_123_match_4_game_1_stats.json"
            self.assertTrue(saved_path.exists())
            self.assertEqual(result["saved"], 1)
            self.assertFalse((Path.cwd() / "data" / saved_path.name).exists())

    def test_forced_live_refresh_does_not_send_cached_etag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            saved_path = Path(temp_dir) / "event_123_match_4_game_1_stats.json"
            saved_path.write_text(json.dumps({
                "matchStatus": 0,
                "homeScore": 0,
                "awayScore": 0,
                "_aclEtag": "pregame-etag",
            }), encoding="utf-8")
            captured_headers = {}

            def fetch(_url, headers):
                captured_headers.update(headers)
                return FakeResponse()

            with patch("match_stats_downloader.fetch_match_stats_response", side_effect=fetch):
                result = fetch_and_save_match_stats("123", [4], force=True, data_dir=temp_dir)

            self.assertEqual(result["saved"], 1)
            self.assertNotIn("if-none-match", captured_headers)

    def test_consolidation_reads_and_writes_same_shared_directory(self):
        payload = {
            "event_match_details": [
                {
                    "playerid": 42,
                    "playerfirstname": "Test",
                    "playerlastname": "Player",
                    "totalpts": 24,
                    "opponentpts": 18,
                    "rounds": 3,
                    "totalbagsin": 6,
                    "totalbagson": 5,
                    "totalbagsoff": 1,
                    "totalfourbaggers": 1,
                    "ptsperrnd": 8.0,
                    "diffperrnd": 2.0,
                }
            ],
            "event_match_inning_history": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "event_123_match_4_game_1_stats.json"
            source.write_text(json.dumps(payload), encoding="utf-8")

            consolidate_tournament_stats("123", data_dir=temp_dir)

            totals = json.loads(
                (Path(temp_dir) / "event_123_player_totals.json").read_text(encoding="utf-8")
            )
            self.assertEqual(totals["42"]["ppr"], 8.0)
            self.assertEqual(totals["42"]["opp_ppr"], 6.0)
            self.assertEqual(totals["42"]["rounds"], 3)


if __name__ == "__main__":
    unittest.main()
