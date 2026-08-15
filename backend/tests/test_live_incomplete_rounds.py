import unittest

from app import normalize_player_totals, normalize_rounds, safe_swap_match_stats


def inning(round_no, player_id, team_id, points, bags_in, bags_on, bags_off):
    return {
        "inningno": round_no,
        "playerid": player_id,
        "teamid": team_id,
        "playerfirstname": f"Player {player_id}",
        "playerlastname": "Test",
        "totalpoints": points,
        "bagsin": bags_in,
        "bagson": bags_on,
        "bagsoff": bags_off,
    }


class LiveIncompleteRoundTests(unittest.TestCase):
    def setUp(self):
        self.details = [
            {"playerid": 10, "teamid": 1, "playerfirstname": "A", "playerlastname": "One", "rounds": 2, "totalpts": 8},
            {"playerid": 20, "teamid": 2, "playerfirstname": "B", "playerlastname": "Two", "rounds": 2, "totalpts": 6},
        ]

    def test_open_zero_placeholder_does_not_reduce_live_ppr(self):
        history = [
            inning(1, 10, 1, 8, 2, 2, 0),
            inning(1, 20, 2, 6, 1, 3, 0),
            inning(2, 10, 1, 0, 0, 0, 0),
            inning(2, 20, 2, 0, 0, 0, 0),
        ]
        players = normalize_player_totals(self.details, history)
        by_id = {player["id"]: player for player in players}

        self.assertEqual(by_id["10"]["rounds"], 1)
        self.assertEqual(by_id["10"]["ppr"], 8.0)
        self.assertEqual(by_id["20"]["rounds"], 1)
        self.assertEqual(by_id["20"]["ppr"], 6.0)
        self.assertEqual(len(normalize_rounds(history)), 1)

    def test_completed_zero_point_wash_still_counts(self):
        history = [
            inning(1, 10, 1, 8, 2, 2, 0),
            inning(1, 20, 2, 6, 1, 3, 0),
            inning(2, 10, 1, 0, 0, 4, 0),
            inning(2, 20, 2, 0, 0, 4, 0),
        ]
        players = normalize_player_totals(self.details, history)
        by_id = {player["id"]: player for player in players}

        self.assertEqual(by_id["10"]["rounds"], 2)
        self.assertEqual(by_id["10"]["ppr"], 4.0)
        self.assertEqual(len(normalize_rounds(history)), 2)

    def test_current_round_is_provisional_even_after_all_bags_are_recorded(self):
        history = [
            inning(1, 10, 1, 8, 2, 2, 0),
            inning(1, 20, 2, 6, 1, 3, 0),
            inning(2, 10, 1, 0, 0, 4, 0),
            inning(2, 20, 2, 0, 0, 4, 0),
        ]
        players = normalize_player_totals(self.details, history, current_round=2, match_is_live=True)
        by_id = {player["id"]: player for player in players}

        self.assertEqual(by_id["10"]["rounds"], 1)
        self.assertEqual(by_id["10"]["ppr"], 8.0)
        self.assertEqual(len(normalize_rounds(history, current_round=2, match_is_live=True)), 1)

        result = safe_swap_match_stats({
            "matchStatus": 0,
            "currentRound": 2,
            "event_match_details": self.details,
            "event_match_inning_history": history,
        })
        safe_by_id = {str(player["playerId"]): player for player in result["players"]}
        self.assertEqual(safe_by_id["10"]["rounds"], 1)
        self.assertEqual(safe_by_id["10"]["ppr"], 8.0)

    def test_swap_live_stats_use_only_completed_innings(self):
        history = [
            inning(1, 10, 1, 8, 2, 2, 0),
            inning(1, 20, 2, 6, 1, 3, 0),
            inning(2, 10, 1, 0, 0, 0, 0),
            inning(2, 20, 2, 0, 0, 0, 0),
        ]
        result = safe_swap_match_stats({
            "event_match_details": self.details,
            "event_match_inning_history": history,
        })
        by_id = {str(player["playerId"]): player for player in result["players"]}

        self.assertEqual(by_id["10"]["rounds"], 1)
        self.assertEqual(by_id["10"]["ppr"], 8.0)


if __name__ == "__main__":
    unittest.main()
