import unittest

from walker_participation import WALKER_PARTICIPATION, transform_walker_payload


class WalkerParticipationTests(unittest.TestCase):
    def test_definitive_ghost_seat_is_attributed_to_real_player(self):
        payload = {
            "event_team_details": [
                {"teamid": 7, "playerid": 230405, "playerfirstname": "JP", "playerlastname": "Parsons"},
                {"teamid": 7, "playerid": 99999, "playerfirstname": "Ghost", "playerlastname": "Player"},
            ],
            "event_match_inning_history": [
                {"teamid": 7, "playerid": 230405, "playerfirstname": "JP", "playerlastname": "Parsons", "inningno": 1, "totalpoints": 8},
                {"teamid": 8, "playerid": 44, "playerfirstname": "Real", "playerlastname": "Opponent", "inningno": 1, "totalpoints": 7},
                {"teamid": 7, "playerid": 99999, "playerfirstname": "Ghost", "playerlastname": "Player", "inningno": 2, "totalpoints": 9},
                {"teamid": 8, "playerid": 45, "playerfirstname": "Other", "playerlastname": "Opponent", "inningno": 2, "totalpoints": 6},
            ],
            "event_match_details": [
                {"teamid": 7, "playerid": 230405, "rounds": 1, "playedinnings": 1, "totalpts": 8},
                {"teamid": 7, "playerid": 99999, "rounds": 1, "playedinnings": 1, "totalpts": 9},
            ],
        }
        transformed, attributions = transform_walker_payload(payload)
        team_seven = [r for r in transformed["event_match_inning_history"] if r["teamid"] == 7]
        self.assertEqual([r["playerid"] for r in team_seven], [230405, 230405])
        self.assertEqual(team_seven[1]["attributed_from_player_id"], 99999)
        self.assertEqual(team_seven[1]["participation_type"], WALKER_PARTICIPATION)
        self.assertEqual(len(transformed["event_team_details"]), 1)
        self.assertEqual(transformed["event_match_details"][0]["rounds"], 2)
        self.assertEqual(transformed["event_match_details"][0]["totalpts"], 17)
        self.assertEqual(attributions[0]["actualPlayerId"], 230405)

    def test_real_player_named_walker_is_never_inferred_as_placeholder(self):
        payload = {
            "event_team_details": [
                {"teamid": 1, "playerid": 12, "playerfirstname": "Alice", "playerlastname": "Walker"},
                {"teamid": 1, "playerid": 13, "playerfirstname": "Bob", "playerlastname": "Jones"},
            ],
            "event_match_inning_history": [],
        }
        transformed, attributions = transform_walker_payload(payload)
        self.assertEqual(attributions, [])
        self.assertEqual(len(transformed["event_team_details"]), 2)


if __name__ == "__main__":
    unittest.main()
