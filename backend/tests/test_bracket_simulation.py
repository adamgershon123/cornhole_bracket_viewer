import unittest

from bracket_simulation import (
    _contextual_king_game_probability,
    _extract_teams,
    _king_seat_position,
    _stage_label,
    _run_template,
)
import random


class BracketSimulationTests(unittest.TestCase):
    def test_double_elimination_final_identifies_king_seat_slot(self):
        template = {
            "matches": {
                "10": {"bracketSide": "W"},
                "11": {"bracketSide": "L"},
                "12": {"bracketSide": "L"},
            },
            "edges": {
                "10:W": {"matchId": 12, "position": "T"},
                "11:W": {"matchId": 12, "position": "B"},
            },
        }
        self.assertEqual(_king_seat_position(template, 12), "T")

    def test_historical_championship_rate_creates_warm_challenger_offset(self):
        per_game = _contextual_king_game_probability(
            0.5,
            {"blendedKingSeatChampionshipRate": 0.72371},
        )
        self.assertAlmostEqual(1 - (1 - per_game) ** 2, 0.72371, places=5)
        self.assertLess(per_game, 0.5)

    def test_team_extraction_preserves_first_bracket_appearance(self):
        details = [
            {
                "bracketmatchid": 2,
                "bracketpos": "M2T",
                "bracketteamid": 20,
                "bracketteamname": "Twenty",
                "player_info": [
                    {"playerid": 2, "firstname": "B", "lastname": "Two"}
                ],
            },
            {
                "bracketmatchid": 1,
                "bracketpos": "M1T",
                "bracketteamid": 10,
                "bracketteamname": "Ten",
                "player_info": [
                    {"playerid": 1, "firstname": "A", "lastname": "One"}
                ],
            },
            {
                "bracketmatchid": 3,
                "bracketpos": "M3T",
                "bracketteamid": 10,
                "bracketteamname": "Ten",
                "player_info": [],
            },
        ]
        teams = _extract_teams(details)
        self.assertEqual([team["teamId"] for team in teams], ["10", "20"])
        self.assertEqual(teams[0]["playerIds"], [1])

    def test_stage_labels_distinguish_finalist_and_champion(self):
        self.assertEqual(_stage_label(3, 5), "Semifinal")
        self.assertEqual(_stage_label(4, 5), "Final")
        self.assertEqual(_stage_label(5, 5), "Champion")

    def test_team_extraction_excludes_acl_bye_placeholders(self):
        details = [
            {
                "bracketmatchid": 1,
                "bracketpos": "M1T",
                "bracketteamid": 10,
                "bracketteamname": "Real Team",
                "player_info": [
                    {"playerid": 1, "firstname": "Real", "lastname": "Player"}
                ],
            },
            {
                "bracketmatchid": 1,
                "bracketpos": "M1B",
                "bracketteamid": 16,
                "bracketteamname": "Team 16",
                "player_info": [
                    {"playerid": 121, "firstname": "Bye", "lastname": "User 121"},
                    {"playerid": 122, "firstname": "Bye", "lastname": "User 122"},
                ],
            },
        ]
        teams = _extract_teams(details)
        self.assertEqual([team["teamId"] for team in teams], ["10"])

    def test_team_extraction_excludes_unresolved_acl_destinations(self):
        details = [
            {
                "bracketmatchid": 1,
                "bracketpos": "M1T",
                "bracketteamid": -1,
                "bracketteamname": "Team -1",
                "player_info": [],
            },
            {
                "bracketmatchid": 1,
                "bracketpos": "M1B",
                "bracketteamid": 10,
                "bracketteamname": "Real Team",
                "player_info": [
                    {"playerid": 1, "firstname": "Real", "lastname": "Player"}
                ],
            },
            {
                "bracketmatchid": 2,
                "bracketpos": "M2T",
                "bracketteamid": 99,
                "bracketteamname": "Unresolved Future Team",
                "player_info": [],
            },
        ]
        teams = _extract_teams(details)
        self.assertEqual([team["teamId"] for team in teams], ["10"])

    def test_double_dip_records_one_or_two_actual_games(self):
        king = {"teamId": "K"}
        challenger = {"teamId": "C"}
        template = {
            "matches": {
                "1": {"roundDescription": "Final", "bracketSide": "F"},
                "2": {"bracketSide": "W"},
                "3": {"bracketSide": "L"},
            },
            "edges": {
                "2:W": {"matchId": 1, "position": "T"},
                "3:W": {"matchId": 1, "position": "B"},
            },
        }
        games = []
        _run_template(
            template,
            {(1, "T"): king, (1, "B"): challenger},
            lambda _a, _b: 0.5,
            random.Random(1),
            championship_context={"blendedKingSeatChampionshipRate": 0.75},
            on_game=lambda a, b, winner, probability: games.append(winner["teamId"]),
        )
        self.assertIn(len(games), (1, 2))


if __name__ == "__main__":
    unittest.main()
