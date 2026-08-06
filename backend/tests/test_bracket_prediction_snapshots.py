from __future__ import annotations

import unittest

from bracket_prediction_snapshots import (
    _timeline_checkpoint_indexes,
    bracket_final_standings,
    bracket_round_progress,
    completed_bracket_matches,
)


def entry(match_id, position, team_id, round_desc, status=5, score=(21, 10), name=None):
    return {
        "bracketmatchid": match_id,
        "bracketpos": f"M{match_id}{position}",
        "bracketteamid": team_id,
        "bracketteamname": name or f"Team {team_id}",
        "player_info": [{"playerid": int(team_id) * 100, "firstname": "Player", "lastname": str(team_id)}] if int(team_id) > 0 else [],
        "rounddesc": round_desc,
        "matchStatusID": status,
        "gameResults": [{
            "gameID": 1,
            "matchStatusID": status,
            "scoreHome": score[0],
            "scoreAway": score[1],
            "matchEndTime": f"2026-08-01T00:{int(match_id):02d}:00+00:00",
        }],
    }


class BracketPredictionSnapshotTests(unittest.TestCase):
    def test_round_progress_excludes_byes_and_champion_placeholder(self) -> None:
        details = [
            entry(1, "T", 1, "Round 1"), entry(1, "B", 2, "Round 1"),
            entry(2, "T", 3, "Round 1"), entry(2, "B", -1, "Round 1", status=1, name="Bye User"),
            entry(3, "T", 1, "Round 2"), entry(3, "B", 3, "Round 2"),
            {"bracketmatchid": 4, "bracketpos": "M4T", "bracketteamid": -1,
             "bracketteamname": "", "rounddesc": "Champion"},
        ]

        progress = bracket_round_progress({"bracketDetails": details})

        self.assertEqual(progress, [
            {"key": "round:1", "title": "Round 1", "totalMatches": 1, "completedMatches": 1},
            {"key": "round:2", "title": "Round 2", "totalMatches": 1, "completedMatches": 1},
        ])

    def test_timeline_uses_round_checkpoints_not_every_match(self) -> None:
        details = [
            entry(1, "T", 1, "Round 1"), entry(1, "B", 2, "Round 1"),
            entry(2, "T", 3, "Round 1"), entry(2, "B", 4, "Round 1"),
            entry(3, "T", 1, "Round 2"), entry(3, "B", 3, "Round 2"),
        ]
        bracket = {"bracketDetails": details}
        completed = completed_bracket_matches(bracket)

        self.assertEqual(_timeline_checkpoint_indexes(bracket, completed), {0, 1, 2})

    def test_double_elimination_final_keeps_reset_as_separate_checkpoint(self) -> None:
        top = entry(3, "T", 1, "FINAL")
        bottom = entry(3, "B", 2, "FINAL")
        games = [
            {"gameID": 1, "scoreHome": 10, "scoreAway": 21, "matchStatusID": 5,
             "matchEndTime": "2026-08-01T00:03:00+00:00"},
            {"gameID": 2, "scoreHome": 21, "scoreAway": 15, "matchStatusID": 5,
             "matchEndTime": "2026-08-01T00:04:00+00:00"},
        ]
        top["gameResults"] = games
        bottom["gameResults"] = games
        top["bracketside"] = bottom["bracketside"] = "L"
        details = [
            entry(1, "T", 2, "Round 1"), entry(1, "B", 3, "Round 1"),
            top, bottom,
        ]
        details[0]["bracketside"] = details[1]["bracketside"] = "L"
        bracket = {"bracketDetails": details}

        completed = completed_bracket_matches(bracket)

        self.assertEqual([row["gameId"] for row in completed[-2:]], [1, 2])
        self.assertTrue(all(row["isChampionshipGame"] for row in completed[-2:]))
        checkpoints = _timeline_checkpoint_indexes(bracket, completed)
        self.assertIn(len(completed) - 2, checkpoints)
        self.assertIn(len(completed) - 1, checkpoints)

    def test_final_standings_rank_champion_then_reverse_elimination_order(self) -> None:
        details = [
            entry(1, "T", 1, "Round 1"), entry(1, "B", 2, "Round 1"),
            entry(2, "T", 3, "Round 1"), entry(2, "B", 4, "Round 1"),
            entry(3, "T", 1, "FINAL"), entry(3, "B", 3, "FINAL"),
        ]
        bracket = {"bracketDetails": details}

        standings = bracket_final_standings(bracket)

        self.assertEqual([row["teamId"] for row in standings], ["1", "3", "4", "2"])
        self.assertEqual([row["place"] for row in standings], [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
