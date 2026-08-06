import sqlite3
import unittest
from unittest.mock import patch

from historical_tournament_replay import (
    historical_tournament_replay_status,
    replay_historical_tournament,
)


class HistoricalTournamentReplayTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    @patch("historical_tournament_replay.simulate_bracket")
    def test_saves_cutoff_safe_forecast_before_archiving_outcome(self, simulate):
        simulate.return_value = {
            "status": "COMPLETE",
            "modelVersion": "test-model",
            "teams": [
                {"teamId": "7", "teamName": "Seven", "players": [], "winEventProbability": 0.6},
                {"teamId": "8", "teamName": "Eight", "players": [], "winEventProbability": 0.4},
            ],
        }
        result = replay_historical_tournament(self.conn, self._payload(), simulations=100)
        self.assertEqual(result["status"], "CREATED")
        snapshot = self.conn.execute(
            "SELECT payload_json FROM bracket_prediction_snapshots WHERE event_id=91"
        ).fetchone()
        self.assertIn('"snapshotOrigin": "HISTORICAL_REPLAY"', snapshot[0])
        self.assertIn('"dataCutoffAt": "2025-10-01T00:00:00+00:00"', snapshot[0])
        outcome = self.conn.execute(
            "SELECT champion_player_ids_json FROM historical_tournament_replay_outcomes WHERE event_id=91"
        ).fetchone()
        self.assertEqual(outcome[0], "[700]")
        self.assertIsNone(simulate.call_args.kwargs["data_dir"])
        self.assertEqual(simulate.call_args.kwargs["completed_match_ids"], [])

    @patch("historical_tournament_replay.simulate_bracket")
    def test_status_separates_replay_and_live_snapshots(self, simulate):
        simulate.return_value = {
            "status": "COMPLETE",
            "teams": [
                {"teamId": "7", "teamName": "Seven", "players": [], "winEventProbability": 0.6},
                {"teamId": "8", "teamName": "Eight", "players": [], "winEventProbability": 0.4},
            ],
        }
        replay_historical_tournament(self.conn, self._payload(), simulations=100)
        status = historical_tournament_replay_status(self.conn)
        self.assertEqual(status["historicalReplaySnapshots"], 1)
        self.assertEqual(status["liveFrozenSnapshots"], 0)

    @staticmethod
    def _payload():
        game = {"gameID": 1, "matchStatusID": 5, "scoreHome": 21, "scoreAway": 10}
        return {
            "eventInfo": {"eventID": 91, "startdate": "2025-10-01"},
            "bracketDetails": [
                {
                    "bracketmatchid": 1, "bracketteamid": 7, "bracketpos": "M1T",
                    "rounddesc": "Final", "matchStatusID": 5, "gameResults": [game],
                    "player_info": [{"playerid": 700, "firstname": "A", "lastname": "One"}],
                },
                {
                    "bracketmatchid": 1, "bracketteamid": 8, "bracketpos": "M1B",
                    "rounddesc": "Final", "matchStatusID": 5, "gameResults": [game],
                    "player_info": [{"playerid": 800, "firstname": "B", "lastname": "Two"}],
                },
            ],
        }


if __name__ == "__main__":
    unittest.main()
