from __future__ import annotations

import unittest

from game_state_reconstruction import (
    INFERRED_FROM_ROTATION,
    INFERRED_FROM_SCORE,
    MANUAL,
    UNKNOWN,
    reconstruct_game_states,
)


def round_row(number, a_player, b_player, scoring_team=None, net=0):
    return {
        "round": number,
        "players": [
            {"playerId": a_player, "teamId": "A"},
            {"playerId": b_player, "teamId": "B"},
        ],
        "scoringTeamId": scoring_team,
        "netPoints": net,
    }


class GameStateReconstructionTests(unittest.TestCase):
    def test_unknown_opening_wash_stays_unknown_until_first_score(self):
        states = reconstruct_game_states([
            round_row(1, "A1", "B1"),
            round_row(2, "A2", "B2", "A", 3),
            round_row(3, "A1", "B1"),
        ])
        self.assertEqual(states[0]["firstThrowTeamStatus"], UNKNOWN)
        self.assertIsNone(states[0]["nextFirstThrowTeamId"])
        self.assertEqual(states[1]["nextFirstThrowTeamId"], "A")
        self.assertEqual(states[1]["nextFirstThrowTeamStatus"], INFERRED_FROM_SCORE)
        self.assertEqual(states[1]["nextFirstThrowPlayerId"], "A1")
        self.assertEqual(states[2]["firstThrowPlayerId"], "A1")

    def test_washes_preserve_last_scoring_team_and_rotate_player(self):
        states = reconstruct_game_states([
            round_row(1, "A1", "B1", "B", 2),
            round_row(2, "A2", "B2"),
            round_row(3, "A1", "B1"),
        ])
        self.assertEqual(states[0]["nextFirstThrowTeamId"], "B")
        self.assertEqual(states[0]["nextFirstThrowPlayerId"], "B2")
        self.assertEqual(states[1]["nextFirstThrowTeamId"], "B")
        self.assertEqual(states[1]["nextFirstThrowPlayerId"], "B1")
        self.assertEqual(states[2]["lastScoringTeamId"], "B")
        self.assertTrue(states[2]["wasWash"])

    def test_manual_opening_player_and_team_are_preserved_as_provenance(self):
        states = reconstruct_game_states(
            [round_row(1, "A1", "B1")],
            opening_first_throw_team_id="A",
            opening_first_throw_player_id="A1",
        )
        self.assertEqual(states[0]["firstThrowTeamStatus"], MANUAL)
        self.assertEqual(states[0]["firstThrowPlayerStatus"], MANUAL)
        self.assertEqual(states[0]["firstThrowPlayerId"], "A1")

    def test_score_and_lead_progression_uses_net_points(self):
        states = reconstruct_game_states([
            round_row(1, "A1", "B1", "A", 4),
            round_row(2, "A2", "B2", "B", 2),
            round_row(3, "A1", "B1", "A", 1),
        ])
        self.assertEqual(states[0]["scoreAfter"], {"A": 4})
        self.assertEqual(states[1]["scoreBefore"], {"A": 4})
        self.assertEqual(states[1]["scoreAfter"], {"A": 4, "B": 2})
        self.assertEqual(states[2]["scoreAfter"], {"A": 5, "B": 2})
        self.assertEqual(states[2]["firstThrowPlayerStatus"], INFERRED_FROM_ROTATION)


if __name__ == "__main__":
    unittest.main()
