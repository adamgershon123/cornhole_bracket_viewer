import unittest

from double_dip_analysis import analyze_double_elimination_final


class DoubleDipAnalysisTests(unittest.TestCase):
    def test_detects_reset_and_king_seat_path(self):
        payload = {
            "eventInfo": {"eventID": 91},
            "bracketDetails": [
                self._row(7, "W", 10, "Winner Final", games=[self._game(1, 21, 10)]),
                self._row(8, "L", 11, "Loser Final", games=[self._game(1, 21, 15)]),
                self._row(7, "L", 12, "Final", "M12T", [self._game(1, 10, 21), self._game(2, 21, 17)]),
                self._row(8, "L", 12, "Final", "M12B", [self._game(1, 10, 21), self._game(2, 21, 17)]),
            ],
        }
        result = analyze_double_elimination_final(payload)
        self.assertTrue(result["resetOccurred"])
        self.assertEqual(result["kingSeatTeamId"], "7")
        self.assertTrue(result["kingSeatWon"])
        self.assertEqual(result["championshipGames"], 2)

    def test_rejects_single_elimination(self):
        payload = {
            "eventInfo": {"eventID": 92},
            "bracketDetails": [
                self._row(7, "W", 1, "Final", "M1T", [self._game(1, 21, 10)]),
                self._row(8, "W", 1, "Final", "M1B", [self._game(1, 21, 10)]),
            ],
        }
        self.assertIsNone(analyze_double_elimination_final(payload))

    @staticmethod
    def _game(game_id, home, away):
        return {
            "gameID": game_id,
            "scoreHome": home,
            "scoreAway": away,
            "matchStatusID": 5,
            "matchStartTime": f"2026-01-01 1{game_id}:00:00",
            "matchEndTime": f"2026-01-01 1{game_id}:15:00",
        }

    @staticmethod
    def _row(team_id, side, match_id, description, position=None, games=None):
        return {
            "bracketteamid": team_id,
            "bracketteamname": f"Team {team_id}",
            "bracketside": side,
            "bracketmatchid": match_id,
            "rounddesc": description,
            "bracketpos": position or f"M{match_id}T",
            "matchStatusID": 5,
            "gameResults": games or [],
            "player_info": [{"playerid": team_id * 100}],
        }


if __name__ == "__main__":
    unittest.main()
