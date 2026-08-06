import sqlite3
import unittest

from tournament_reforecast import checkpoint_team_form


class TournamentReforecastTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE player_rounds(
              event_id INTEGER, match_id TEXT, player_id INTEGER,
              gross_points INTEGER, net_points INTEGER,
              round_result TEXT, four_bagger INTEGER
            )
            """
        )
        self.teams = [{"teamId": "9", "playerIds": [101, 102]}]

    def tearDown(self):
        self.conn.close()

    def test_frozen_checkpoint_excludes_all_current_event_rounds(self):
        self._rounds("1", 101, [12, 12])
        result = checkpoint_team_form(
            self.conn,
            event_id=77,
            teams=self.teams,
            completed_match_ids=[],
            historical_team_ppr={"9": 7.0},
        )["9"]
        self.assertEqual(result["eventRounds"], 0)
        self.assertEqual(result["adjustedPpr"], 7.0)

    def test_checkpoint_cannot_see_later_matches(self):
        self._rounds("1", 101, [8, 8])
        self._rounds("2", 101, [12, 12, 12])
        result = checkpoint_team_form(
            self.conn,
            event_id=77,
            teams=self.teams,
            completed_match_ids=["1"],
            historical_team_ppr={"9": 7.0},
        )["9"]
        self.assertEqual(result["eventRounds"], 2)
        self.assertEqual(result["eventPpr"], 8.0)

    def test_small_samples_are_shrunk_toward_history(self):
        self._rounds("1", 101, [12])
        result = checkpoint_team_form(
            self.conn,
            event_id=77,
            teams=self.teams,
            completed_match_ids=["1"],
            historical_team_ppr={"9": 7.0},
        )["9"]
        self.assertEqual(result["sampleWeight"], round(1 / 41, 6))
        self.assertLess(result["adjustedPpr"], 7.2)

    def _rounds(self, match_id, player_id, gross_values):
        self.conn.executemany(
            "INSERT INTO player_rounds VALUES(77,?,?,?,?,?,?)",
            [
                (str(match_id), player_id, gross, gross - 7, "W", int(gross == 12))
                for gross in gross_values
            ],
        )


if __name__ == "__main__":
    unittest.main()
