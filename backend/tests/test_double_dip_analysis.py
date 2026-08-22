import sqlite3
import unittest

from double_dip_analysis import (
    analyze_double_elimination_final,
    championship_double_dip_profile,
    double_dip_baseline,
    store_double_dip_records,
)


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

    def test_player_profiles_use_role_specific_championship_outcomes(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        payloads = [
            self._payload(91, [(21, 10)]),
            self._payload(92, [(10, 21), (21, 17)]),
            self._payload(93, [(10, 21), (15, 21)]),
        ]
        records = [analyze_double_elimination_final(payload) for payload in payloads]
        store_double_dip_records(conn, records)
        result = championship_double_dip_profile(
            conn,
            payload=payloads[-1],
            match_id=12,
            persist_completed=True,
        )

        king = result["kingSeat"]
        challenger = result["challenger"]
        self.assertEqual(king["combinedHistory"]["appearances"], 3)
        self.assertAlmostEqual(king["combinedHistory"]["winInOneRate"], 1 / 3)
        self.assertAlmostEqual(king["combinedHistory"]["winInTwoRate"], 1 / 3)
        self.assertAlmostEqual(king["combinedHistory"]["doubleDippedRate"], 1 / 3)
        self.assertAlmostEqual(challenger["combinedHistory"]["loseFirstRate"], 1 / 3)
        self.assertAlmostEqual(challenger["combinedHistory"]["loseSecondRate"], 1 / 3)
        self.assertAlmostEqual(challenger["combinedHistory"]["completeDoubleDipRate"], 1 / 3)

    def test_viewer_profile_does_not_persist_completed_event(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        payload = self._payload(91, [(21, 10)])

        result = championship_double_dip_profile(conn, payload=payload, match_id=12)

        self.assertIsNotNone(result)
        count = conn.execute("SELECT COUNT(*) FROM double_dip_events").fetchone()[0]
        self.assertEqual(count, 0)

    def test_historical_baseline_excludes_future_championships(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        early = analyze_double_elimination_final(self._payload(91, [(21, 10)]))
        early["eventDate"] = "2025-01-01"
        future = analyze_double_elimination_final(self._payload(92, [(10, 21), (15, 21)]))
        future["eventDate"] = "2026-01-01"
        store_double_dip_records(conn, [early, future])
        baseline = double_dip_baseline(conn, venue_key="Unknown venue", cutoff_date="2025-06-01")
        self.assertEqual(baseline["overallEvents"], 1)
        self.assertEqual(baseline["overallKingSeatChampionshipRate"], 1.0)

    def _payload(self, event_id, scores):
        games = [self._game(index, home, away) for index, (home, away) in enumerate(scores, start=1)]
        return {
            "eventInfo": {"eventID": event_id},
            "bracketDetails": [
                self._row(7, "W", 10, "Winner Final", games=[self._game(1, 21, 10)]),
                self._row(8, "L", 11, "Loser Final", games=[self._game(1, 21, 15)]),
                self._row(7, "L", 12, "Final", "M12T", games),
                self._row(8, "L", 12, "Final", "M12B", games),
            ],
        }

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
