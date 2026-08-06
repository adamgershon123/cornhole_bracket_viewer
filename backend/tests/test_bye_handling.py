from __future__ import annotations

import unittest

from app import derive_tournament_match_results
from season_platform import match_is_bye


def bracket_entry(
    *,
    match_id: int,
    position: str,
    team_id: int,
    team_name: str,
    player_id: int,
    first_name: str,
    last_name: str,
    home_score: int = 0,
    away_score: int = 0,
) -> dict:
    return {
        "bracketmatchid": match_id,
        "bracketpos": position,
        "bracketteamid": team_id,
        "bracketteamname": team_name,
        "matchStatusID": 5,
        "rounddesc": "Winner Round 1",
        "scores": [{"scorehome": home_score, "scoreaway": away_score}],
        "player_info": [
            {
                "playerid": player_id,
                "firstname": first_name,
                "lastname": last_name,
            }
        ],
    }


class ByeHandlingTests(unittest.TestCase):
    def test_bye_is_detected_from_team_or_player_name(self) -> None:
        pair = [
            bracket_entry(
                match_id=1,
                position="T",
                team_id=10,
                team_name="Real Team",
                player_id=100,
                first_name="Real",
                last_name="Player",
            ),
            bracket_entry(
                match_id=1,
                position="B",
                team_id=11,
                team_name="Team 11",
                player_id=101,
                first_name="Bye User",
                last_name="121",
            ),
        ]

        self.assertTrue(match_is_bye(pair))

    def test_completed_bye_does_not_count_as_player_win(self) -> None:
        real = bracket_entry(
            match_id=1,
            position="T",
            team_id=10,
            team_name="Real Team",
            player_id=100,
            first_name="Real",
            last_name="Player",
            home_score=1,
            away_score=0,
        )
        bye = bracket_entry(
            match_id=1,
            position="B",
            team_id=11,
            team_name="Bye",
            player_id=101,
            first_name="Bye User",
            last_name="121",
            home_score=1,
            away_score=0,
        )

        results = derive_tournament_match_results({"bracketDetails": [real, bye]})

        self.assertNotIn("100", results)
        self.assertNotIn("101", results)

    def test_real_completed_match_still_counts(self) -> None:
        top = bracket_entry(
            match_id=2,
            position="T",
            team_id=12,
            team_name="Top Team",
            player_id=102,
            first_name="Top",
            last_name="Player",
            home_score=21,
            away_score=15,
        )
        bottom = bracket_entry(
            match_id=2,
            position="B",
            team_id=13,
            team_name="Bottom Team",
            player_id=103,
            first_name="Bottom",
            last_name="Player",
            home_score=21,
            away_score=15,
        )

        results = derive_tournament_match_results({"bracketDetails": [top, bottom]})

        self.assertEqual(results["102"]["match_wins"], 1)
        self.assertEqual(results["102"]["match_losses"], 0)
        self.assertEqual(results["103"]["match_wins"], 0)
        self.assertEqual(results["103"]["match_losses"], 1)


if __name__ == "__main__":
    unittest.main()
